"""The CMS API publishes approved practice questions: it may write data/*.questions.json and nothing else under data/."""
from __future__ import annotations

import json
from typing import Any

import pytest
from aws_cdk.assertions import Template

from sound_along.iam_util import API_QUESTIONS_KEY
from tests.helpers import synth

ROLE_PREFIX = {"lambda": "ApiFunctionServiceRole", "ec2": "CmsVmInstanceRole"}


def _api_statements(template: Template, mode: str) -> list[dict[str, Any]]:
    policies = [
        p for p in template.find_resources("AWS::IAM::Policy").values()
        if any(r["Ref"].startswith(ROLE_PREFIX[mode]) for r in p["Properties"]["Roles"])
    ]
    return [s for p in policies for s in p["Properties"]["PolicyDocument"]["Statement"]]


def _actions(statement: dict[str, Any]) -> list[str]:
    action = statement["Action"]
    return [action] if isinstance(action, str) else list(action)


def _text(value: Any) -> str:
    return json.dumps(value, default=str)


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_can_write_only_the_approved_questions_file_under_data(mode: str) -> None:
    statements = _api_statements(synth(mode), mode)
    data_writes = [s for s in statements if "/data/" in _text(s["Resource"])]
    assert len(data_writes) == 1
    assert _actions(data_writes[0]) == ["s3:PutObject"]
    assert "/" + API_QUESTIONS_KEY in _text(data_writes[0]["Resource"])
    assert API_QUESTIONS_KEY == "data/*.questions.json"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_cannot_read_or_delete_anything_under_data(mode: str) -> None:
    for s in _api_statements(synth(mode), mode):
        if "/data/" in _text(s.get("Resource")):
            assert set(_actions(s)) == {"s3:PutObject"}, s
