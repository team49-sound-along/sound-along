"""READER_INSIGHTS (anonymous per-reader progress codes in the read-aloud insights) is OFF in a deployed stack unless -c readerInsights=true.

Reader codes must not be collected on a deployed site before teacher sign-in exists, so the default is off for both hosts.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from sound_along.config import parse_reader_insights
from tests.helpers import synth


def _api_env(mode: str, **kwargs: Any) -> str:
    template = synth(mode, **kwargs)
    if mode == "lambda":
        fns = [f for f in template.find_resources("AWS::Lambda::Function").values() if f["Properties"].get("Handler") == "src/index.handler"]
        assert len(fns) == 1
        return str(fns[0]["Properties"]["Environment"]["Variables"].get("READER_INSIGHTS"))
    instances = list(template.find_resources("AWS::EC2::Instance").values())
    assert len(instances) == 1
    user_data = json.dumps(instances[0]["Properties"]["UserData"]).replace("\\n", "\n")
    return "true" if "Environment=READER_INSIGHTS=true" in user_data else "false" if "Environment=READER_INSIGHTS=false" in user_data else "missing"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_reader_insights_is_off_by_default(mode: str) -> None:
    assert _api_env(mode) == "false"


@pytest.mark.parametrize("mode", ["lambda", "ec2"])
def test_reader_insights_is_on_only_when_the_context_asks_for_it(mode: str) -> None:
    assert _api_env(mode, reader_insights=True) == "true"


def test_only_the_exact_value_true_turns_it_on() -> None:
    assert [parse_reader_insights(v) for v in (None, "false", "no", "1", "TRUE ", "yes", "true", True)] == [False, False, False, False, False, False, True, True]
