"""The model comparison: rows, table, failures, caps. No network: every model is a pretend one."""
import json

from conftest import PretendModel, make_timing
from qg_adapters import AdapterError, BedrockAdapter, ModelReply
from qg_bakeoff import DEFAULT_MODELS, format_table, main, summarize
from qg_cost import price_for

GOOD = {"skill": "literal", "question": "Where is Piedmont Park?", "choices": ["In Atlanta, Georgia.", "In a small town.", "Far from any city."],
        "answerIndex": 0, "evidenceQuote": "In Atlanta, Georgia, there is a big park", "evidenceSentence": 2}
TRUTH = {"Where is Piedmont Park?": "In Atlanta, Georgia."}


class ManyPassages(PretendModel):
    """Like PretendModel, but every generation request starts a fresh passage, so one adapter can serve several passages."""

    def complete(self, system, user, **kwargs):
        if "Write up to" in user:
            self.calls = []
        return super().complete(system, user, **kwargs)


def pretend():
    return ManyPassages(ModelReply(json.dumps({"questions": [GOOD]}), 900, 400), TRUTH)


def write_timing(tmp_path, name="a"):
    path = tmp_path / f"{name}.timing.json"
    path.write_text(json.dumps(make_timing(passage_id=name)))
    return path


def test_the_three_default_models_are_nova_lite_nova_pro_and_llama4_maverick():
    assert [m.split(":", 1)[1] for m in DEFAULT_MODELS] == [
        "amazon.nova-lite-v1:0", "amazon.nova-pro-v1:0", "meta.llama4-maverick-17b-instruct-v1:0"]
    assert all(price_for(m) is not None for m in DEFAULT_MODELS)  # every default model has a price, so cost is never "unknown" by accident


def test_summary_counts_kept_dropped_tokens_and_cost(tmp_path):
    out = tmp_path / "out"
    code = main(["--timing", str(write_timing(tmp_path)), "--models", DEFAULT_MODELS[0], "--out", str(out)], adapter_factory=lambda s, r: pretend())
    assert code == 0
    rows = json.loads((out / "bakeoff.summary.json").read_text())
    row = rows[0]
    assert (row["kept"], row["dropped"], row["passagesFailed"]) == (1, 0, 0)
    assert row["inputTokens"] > 0 and row["costPerPassageUsd"] > 0
    assert list(out.glob("*/*.draft.json")), "each model's drafts are written to its own folder for a person to read"


def test_a_failed_passage_is_reported_and_makes_the_exit_code_nonzero(tmp_path):
    class Broken:
        def complete(self, *a, **k):
            raise AdapterError("ThrottlingException")
    code = main(["--timing", str(write_timing(tmp_path)), "--models", DEFAULT_MODELS[0], "--out", str(tmp_path / "o")], adapter_factory=lambda s, r: Broken())
    assert code == 1


def test_the_limit_caps_passages_per_model(tmp_path):
    files = [str(write_timing(tmp_path, n)) for n in "abcd"]
    out = tmp_path / "o"
    main(["--timing", *files, "--models", DEFAULT_MODELS[0], "--out", str(out), "--limit", "2"], adapter_factory=lambda s, r: pretend())
    assert json.loads((out / "bakeoff.summary.json").read_text())[0]["passages"] == 2


def test_no_schema_switches_schema_mode_off_for_bedrock(tmp_path):
    made = []
    def factory(spec, region):
        adapter = BedrockAdapter("us.amazon.nova-lite-v1:0", client=object(), sleep=lambda s: None)
        made.append(adapter)
        return adapter
    main(["--timing", str(write_timing(tmp_path)), "--models", DEFAULT_MODELS[0], "--out", str(tmp_path / "o"), "--no-schema"], adapter_factory=factory)
    assert made[0].use_schema is False


def test_table_lists_each_model_and_warns_that_kept_is_not_good():
    drafts = [{"questions": [], "dropped": [{"question": "q", "reasons": ["the evidence quote is not in the passage"]}],
               "metrics": {"inputTokens": 10, "outputTokens": 5, "seconds": 1.5}}]
    row = summarize("bedrock:us.amazon.nova-lite-v1:0", drafts, ["x.json: boom"], passages=2)
    assert row["droppedQuoteNotFound"] == 1 and row["passagesFailed"] == 1
    text = format_table([row])
    assert "nova-lite" in text and "FAILED" in text and "Kept does not mean good" in text
