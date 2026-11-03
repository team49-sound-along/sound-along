"""The CMS API's S3 permissions: complete enough to avoid 403-for-a-missing-key, and still narrow."""
from __future__ import annotations

import json
from typing import Any

import pytest
from aws_cdk.assertions import Template

from sound_along.iam_util import API_MANIFEST_KEY, API_RAW_PREFIX
from tests.helpers import actions_for_roles_starting_with, synth


def _statements(template: Template) -> list[dict[str, Any]]:
    return [s for p in template.find_resources("AWS::IAM::Policy").values() for s in p["Properties"]["PolicyDocument"]["Statement"]]


def _actions(statement: dict[str, Any]) -> list[str]:
    action = statement["Action"]
    return [action] if isinstance(action, str) else list(action)


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_role_can_list_only_the_prefixes_it_reads_so_a_missing_key_is_a_404_not_a_403(mode: str) -> None:
    lists = [s for s in _statements(synth(mode)) if "s3:ListBucket" in _actions(s)]
    prefixes = [set(s["Condition"]["StringLike"]["s3:prefix"]) for s in lists if "Condition" in s]
    assert any({API_RAW_PREFIX, API_MANIFEST_KEY} <= p for p in prefixes), prefixes


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_role_reads_raw_inputs_and_the_listening_manifest_and_nothing_broader(mode: str) -> None:
    template = synth(mode)
    role_prefix = "ApiFunctionServiceRole" if mode == "lambda" else "CmsVmInstanceRole"
    actions = actions_for_roles_starting_with(template, role_prefix)
    assert {a for a in actions if a.startswith("s3:")} >= {"s3:PutObject", "s3:GetObject", "s3:ListBucket"}
    assert not [a for a in actions if a in ("s3:*", "s3:Get*", "s3:Put*", "s3:List*", "s3:DeleteObject")]
    statements = _statements(template)
    resources = json.dumps([s["Resource"] for s in statements if "s3:GetObject" in _actions(s)], default=str)
    assert "/raw/*" in resources and API_MANIFEST_KEY in resources
    for s in statements:
        if "s3:ListBucket" in _actions(s):
            assert "Condition" in s, "ListBucket must always be limited to prefixes"


def test_constants_name_exactly_what_the_api_touches() -> None:
    assert API_RAW_PREFIX == "raw/*" and API_MANIFEST_KEY == "raw/ab/manifest.json"
