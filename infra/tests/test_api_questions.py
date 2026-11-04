"""The CMS API publishes approved practice questions: it may write data/*.questions.json and nothing else under data/."""
from __future__ import annotations

import json
from typing import Any

import pytest
from aws_cdk.assertions import Template

from sound_along.iam_util import API_INDEX_KEY, API_PASSAGE_FILE_KEYS, API_QUESTIONS_KEY, API_TIMING_KEY
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
def test_api_can_write_only_the_approved_questions_file_and_the_library_list_under_data(mode: str) -> None:
    """data/*.questions.json (a teacher publishes questions) and data/index.json (published again after a teacher deletes a passage)."""
    statements = _api_statements(synth(mode), mode)
    data_writes = [s for s in statements if "/data/" in _text(s["Resource"]) and "s3:PutObject" in _actions(s)]
    assert len(data_writes) == 2
    assert all(_actions(s) == ["s3:PutObject"] for s in data_writes)
    resources = sorted(_text(s["Resource"]) for s in data_writes)
    assert any("/" + API_QUESTIONS_KEY in r for r in resources) and any("/" + API_INDEX_KEY in r for r in resources)
    assert API_QUESTIONS_KEY == "data/*.questions.json" and API_INDEX_KEY == "data/index.json"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_cannot_read_or_delete_anything_under_data_except_timing_files_and_a_passages_own_files(mode: str) -> None:
    """The one read under data/ is data/*.timing.json (word lookup for anonymous read-aloud results); the one delete is a passage's own files
    (a teacher removes it from the Library); see test_iam_s3.py."""
    for s in _api_statements(synth(mode), mode):
        if "/data/" in _text(s.get("Resource")):
            assert set(_actions(s)) in ({"s3:PutObject"}, {"s3:GetObject"}, {"s3:DeleteObject"}), s
            if "s3:GetObject" in _actions(s):
                assert "/" + API_TIMING_KEY in _text(s["Resource"]), s
            if "s3:DeleteObject" in _actions(s):
                assert len(s["Resource"]) == len(API_PASSAGE_FILE_KEYS), s
                assert all(any("/" + key in _text(r) for key in API_PASSAGE_FILE_KEYS) for r in s["Resource"]), s
