"""The CMS API's S3 permissions: complete enough to avoid 403-for-a-missing-key, and still narrow."""
from __future__ import annotations

import json
from typing import Any

import pytest
from aws_cdk.assertions import Template

from sound_along.iam_util import API_INDEX_KEY, API_MANIFEST_KEY, API_PASSAGE_FILE_KEYS, API_RAW_PREFIX
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
    assert not [a for a in actions if a in ("s3:*", "s3:Get*", "s3:Put*", "s3:List*", "s3:Delete*")]
    statements = _statements(template)
    resources = json.dumps([s["Resource"] for s in statements if "s3:GetObject" in _actions(s)], default=str)
    assert "/raw/*" in resources and API_MANIFEST_KEY in resources
    for s in statements:
        if "s3:ListBucket" in _actions(s):
            assert "Condition" in s, "ListBucket must always be limited to prefixes"


def test_constants_name_exactly_what_the_api_touches() -> None:
    assert API_RAW_PREFIX == "raw/*" and API_MANIFEST_KEY == "raw/ab/manifest.json"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_the_generator_can_read_data_so_translation_linking_and_the_unchanged_check_work_on_aws(mode: str) -> None:
    """process_translation, _previous_timing and _cards_reviewed all READ data/*. Without GetObject (and ListBucket, so a missing key is a 404 and
    not a 403 that the code swallows) the translation would exist on AWS but never be linked, and translated cards would never be made."""
    statements = [s for s in _statements(synth(mode)) if any(a in _actions(s) for a in ("s3:GetObject", "s3:PutObject", "s3:ListBucket"))]
    template = synth(mode)
    from tests.helpers import actions_for_roles_starting_with  # noqa: F401

    roles = [p for p in template.find_resources("AWS::IAM::Policy").values() if any(r["Ref"].startswith("GeneratorFunctionServiceRole") for r in p["Properties"]["Roles"])]
    grants = [s for p in roles for s in p["Properties"]["PolicyDocument"]["Statement"]]
    reads = [s for s in grants if "s3:GetObject" in _actions(s)]
    assert any("/data/*" in json.dumps(s["Resource"]) for s in reads), "the generator must be able to read data/*"
    assert any("/raw/*" in json.dumps(s["Resource"]) for s in reads), "and still read its job inputs under raw/*"
    lists = [s for s in grants if "s3:ListBucket" in _actions(s)]
    assert lists and "data/*" in json.dumps(lists[0]["Condition"]["StringLike"]["s3:prefix"])
    assert not [a for s in grants for a in _actions(s) if a in ("s3:*", "s3:Get*", "s3:Put*", "s3:List*")]
    puts = [s for s in grants if "s3:PutObject" in _actions(s)]
    assert puts and all(("/data/*" in json.dumps(s["Resource"]) or "/raw/work/*" in json.dumps(s["Resource"])) and "/raw/*" not in json.dumps(s["Resource"]) for s in puts), "writes stay on data/* and the private work folder only"
    deletes = [s for s in grants if "s3:DeleteObject" in _actions(s)]
    assert deletes and all("/raw/work/*" in json.dumps(s["Resource"]) and "/data/" not in json.dumps(s["Resource"]) for s in deletes), "it can only delete from the work folder it cleans up"
    assert "raw/work/*" in json.dumps(lists[0]["Condition"]["StringLike"]["s3:prefix"]), "and list that folder to clean it"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_reads_only_timing_files_under_data_so_a_read_aloud_word_is_looked_up_on_the_server(mode: str) -> None:
    """Read-aloud results name a word by position; the API resolves the text from data/<id>.timing.json. That is the ONLY data/ file it may read:
    audio, cards and questions stay unreadable, and it still cannot write anything under data/ except the questions file."""
    from sound_along.iam_util import API_QUESTIONS_KEY, API_TIMING_KEY

    template = synth(mode)
    role_prefix = "ApiFunctionServiceRole" if mode == "lambda" else "CmsVmInstanceRole"
    policies = [
        p for p in template.find_resources("AWS::IAM::Policy").values()
        if any(str(r.get("Ref", "")).startswith(role_prefix) for r in p["Properties"]["Roles"])
    ]
    grants = [s for p in policies for s in p["Properties"]["PolicyDocument"]["Statement"]]
    data_reads = [s for s in grants if "s3:GetObject" in _actions(s) and "/data/" in json.dumps(s["Resource"], default=str)]
    assert data_reads, "the API must be able to read timing files"
    for s in data_reads:
        assert _actions(s) == ["s3:GetObject"]
        assert API_TIMING_KEY in json.dumps(s["Resource"], default=str)
    data_writes = [s for s in grants if "s3:PutObject" in _actions(s) and "/data/" in json.dumps(s["Resource"], default=str)]
    assert all(API_QUESTIONS_KEY in json.dumps(s["Resource"], default=str) or API_INDEX_KEY in json.dumps(s["Resource"], default=str) for s in data_writes)


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_api_can_delete_only_the_per_passage_files_so_a_teacher_can_remove_a_passage(mode: str) -> None:
    """DELETE /api/passages/:id removes data/<id>.<suffix> and publishes data/index.json again. The delete is limited to those names: never the
    index, the pictures (content-hashed, possibly shared), raw/ inputs or anything else; and the index is the only new data/ write."""
    template = synth(mode)
    role_prefix = "ApiFunctionServiceRole" if mode == "lambda" else "CmsVmInstanceRole"
    policies = [
        p for p in template.find_resources("AWS::IAM::Policy").values()
        if any(str(r.get("Ref", "")).startswith(role_prefix) for r in p["Properties"]["Roles"])
    ]
    grants = [s for p in policies for s in p["Properties"]["PolicyDocument"]["Statement"]]
    deletes = [s for s in grants if "s3:DeleteObject" in _actions(s)]
    assert deletes, "the API must be able to delete a passage's files"
    for s in deletes:
        assert _actions(s) == ["s3:DeleteObject"]
        resources = json.dumps(s["Resource"], default=str)
        for key in API_PASSAGE_FILE_KEYS:
            assert key in resources, key
        assert "/raw/" not in resources and "data/*\"" not in resources and API_INDEX_KEY not in resources
    writes = json.dumps([s["Resource"] for s in grants if "s3:PutObject" in _actions(s)], default=str)
    assert API_INDEX_KEY in writes, "the Library list is published again after a delete"
