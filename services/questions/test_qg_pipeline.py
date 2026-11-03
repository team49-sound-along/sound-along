"""End to end with a fake model: generate, validate, shuffle, verify, draft, report, approve."""
import json

import pytest

from conftest import PretendModel, make_timing
from qg_adapters import FakeAdapter, ModelReply
from qg_approve import approve_draft, approve_file
from qg_cost import price_for
from qg_pipeline import GenerationError, generate_draft
from qg_run import format_report, main


def question(text, choices, answer, evidence, skill="literal"):
    return {"skill": skill, "question": text, "choices": choices, "answerIndex": answer, "evidenceSentence": evidence}


GOOD_1 = question("Where is Piedmont Park?", ["In Atlanta, Georgia.", "In a small town.", "Far from any city."], 0, 2)
GOOD_2 = question("What can people do on the grass?", ["Play.", "Sleep all day.", "Build a house."], 0, 1)
BAD_EVIDENCE = question("When do families visit?", ["On weekends.", "On school days.", "Never."], 0, 99)


def generation_reply(*questions):
    return ModelReply(json.dumps({"questions": list(questions)}), 900, 400)


def run(adapter, n=4):
    return generate_draft(make_timing(), adapter, n=n, seed=7, model="ollama:gpt-oss:20b",
                          price=price_for("ollama:gpt-oss:20b"), today="2026-11-03", clock=iter([0.0, 12.5]).__next__)


TRUTH = {"Where is Piedmont Park?": "In Atlanta, Georgia.", "What can people do on the grass?": "Play."}


def test_a_draft_keeps_checked_questions_and_drops_the_rest():
    draft = run(PretendModel(generation_reply(GOOD_1, GOOD_2, BAD_EVIDENCE), TRUTH))
    assert draft["status"] == "draft" and draft["passageId"] == "p-1" and draft["sentenceCount"] == 4
    assert [q["question"] for q in draft["questions"]] == ["Where is Piedmont Park?", "What can people do on the grass?"]
    assert [q["id"] for q in draft["questions"]] == ["q1", "q2"]
    assert all(q["review"] == {"status": "pending"} for q in draft["questions"])
    assert all(q["checks"] == {"answeredFromPassage": True, "guessableWithoutPassage": False} for q in draft["questions"])
    assert draft["dropped"][0]["question"] == "When do families visit?"
    assert any("evidence" in reason for reason in draft["dropped"][0]["reasons"])
    for q in draft["questions"]:  # the right answer is wherever the shuffle put it
        assert q["choices"][q["answerIndex"]] == TRUTH[q["question"]]


def test_a_question_the_model_can_guess_without_the_passage_is_kept_but_flagged():
    draft = run(PretendModel(generation_reply(GOOD_1), TRUTH, without_passage="right"))
    assert draft["questions"][0]["checks"]["guessableWithoutPassage"] is True


def test_a_question_the_model_cannot_answer_from_the_passage_is_dropped_with_a_reason():
    draft = run(PretendModel(generation_reply(GOOD_1), TRUTH, with_passage="wrong"))
    assert draft["questions"] == []
    assert "answer" in " ".join(draft["dropped"][0]["reasons"]).lower()


def test_duplicate_questions_are_dropped():
    draft = run(PretendModel(generation_reply(GOOD_1, GOOD_1), TRUTH))
    assert len(draft["questions"]) == 1
    assert any("duplicate" in reason for reason in draft["dropped"][0]["reasons"])


def test_metrics_count_every_call_and_price_them_with_the_basis():
    draft = run(PretendModel(generation_reply(GOOD_1), TRUTH))  # generation 900 in / 400 out, then two checks of 50 in / 4 out
    metrics = draft["metrics"]
    assert metrics["calls"] == 3
    assert metrics["inputTokens"] == 900 + 50 + 50 and metrics["outputTokens"] == 400 + 4 + 4
    assert metrics["seconds"] == 12.5
    assert metrics["estimatedCostUsd"] == pytest.approx(1000 * 0.0721 / 1e6 + 408 * 0.3090 / 1e6)
    assert "Sydney" in metrics["priceBasis"]
    assert draft["generatedWith"]["model"] == "ollama:gpt-oss:20b" and draft["generatedWith"]["promptVersion"]


def test_unparseable_generation_raises_a_clear_error():
    with pytest.raises(GenerationError, match="JSON"):
        run(FakeAdapter([ModelReply("sorry I cannot", 10, 3)]))


def test_an_empty_question_list_is_an_error_not_an_empty_success():
    with pytest.raises(GenerationError, match="no questions"):
        run(FakeAdapter([generation_reply()]))


def test_the_requested_count_is_capped():
    adapter = PretendModel(generation_reply(GOOD_1), TRUTH)
    run(adapter, n=50)
    assert "6" in adapter.calls[0][1]  # asked for at most 6, never 50


# ---- approve -------------------------------------------------------------------------------------------------------
def sample_draft():
    return {
        "version": 1, "passageId": "p-1", "title": "Park Day", "sentenceCount": 4, "status": "draft",
        "generatedWith": {"model": "m", "promptVersion": "q1", "date": "2026-11-03"},
        "questions": [
            {"id": "q1", "skill": "literal", "question": "Where is Piedmont Park?", "choices": ["In Atlanta, Georgia.", "In a small town.", "Far from any city."],
             "answerIndex": 0, "evidenceSentence": 2, "checks": {"answeredFromPassage": True, "guessableWithoutPassage": False}, "review": {"status": "approved"}},
            {"id": "q2", "skill": "literal", "question": "What can people do on the grass?", "choices": ["Play.", "Sleep.", "Build."],
             "answerIndex": 0, "evidenceSentence": 1, "checks": {"answeredFromPassage": True, "guessableWithoutPassage": True}, "review": {"status": "pending"}},
        ],
        "dropped": [{"question": "x", "reasons": ["y"]}], "metrics": {"calls": 3},
    }


def test_approve_keeps_only_approved_questions_and_strips_internal_fields():
    served = approve_draft(sample_draft(), today="2026-11-04")
    assert [q["id"] for q in served["questions"]] == ["q1"]
    assert set(served["questions"][0]) == {"id", "skill", "question", "choices", "answerIndex", "evidenceSentence"}
    assert served["reviewed"] is True  # same convention as the cards documents
    assert served["reviewedAt"] == "2026-11-04" and "dropped" not in served and "metrics" not in served and "status" not in served
    assert served["passageId"] == "p-1" and served["version"] == 1


def test_approve_refuses_a_draft_with_nothing_approved():
    draft = sample_draft()
    draft["questions"][0]["review"]["status"] = "pending"
    with pytest.raises(ValueError, match="approved"):
        approve_draft(draft, today="d")


def test_approve_rechecks_the_questions_before_publishing():
    draft = sample_draft()
    draft["questions"][0]["evidenceSentence"] = 40
    with pytest.raises(ValueError, match="evidence"):
        approve_draft(draft, today="d")


def test_approve_file_writes_only_the_approved_document_to_the_data_folder(tmp_path):
    drafts, data = tmp_path / "questions", tmp_path / "data"
    drafts.mkdir(), data.mkdir()
    (drafts / "p-1.draft.json").write_text(json.dumps(sample_draft()))
    out = approve_file(drafts / "p-1.draft.json", data, today="2026-11-04")
    assert out == data / "p-1.questions.json"
    assert json.loads(out.read_text())["questions"][0]["id"] == "q1"
    assert sorted(p.name for p in data.iterdir()) == ["p-1.questions.json"]


# ---- report + cli --------------------------------------------------------------------------------------------------
def test_the_report_lists_questions_drops_and_cost():
    text = format_report(sample_draft() | {"metrics": {"calls": 3, "inputTokens": 970, "outputTokens": 408, "seconds": 12.5, "estimatedCostUsd": 0.0002, "priceBasis": "test basis"}})
    assert "Where is Piedmont Park?" in text and "dropped" in text.lower()
    assert "970" in text and "408" in text and "test basis" in text
    assert "guessable" in text.lower()


def test_cli_writes_the_draft_to_the_unserved_folder_and_respects_the_passage_limit(tmp_path, monkeypatch):
    timing_files = []
    for n in range(3):
        path = tmp_path / f"t{n}.timing.json"
        path.write_text(json.dumps(make_timing(passage_id=f"id-{n}")))
        timing_files.append(str(path))
    out = tmp_path / "samples" / "questions"
    adapter = PretendModel(generation_reply(GOOD_1), TRUTH)
    code = main(["--timing", *timing_files, "--model", "ollama:gpt-oss:20b", "--out", str(out), "--limit", "1"], adapter_factory=lambda spec, region: adapter)
    assert code == 0
    assert [p.name for p in out.iterdir()] == ["id-0.draft.json"]  # only one passage because of --limit


def test_a_paraphrase_of_an_earlier_question_is_dropped_as_too_similar():
    paraphrase = question("In which city is Piedmont Park located?", ["In Atlanta, Georgia.", "In a small town.", "Far from any city."], 0, 2)
    truth = {**TRUTH, "In which city is Piedmont Park located?": "In Atlanta, Georgia."}
    draft = run(PretendModel(generation_reply(GOOD_1, paraphrase, GOOD_2), truth))
    assert [q["question"] for q in draft["questions"]] == ["Where is Piedmont Park?", "What can people do on the grass?"]
    assert any("similar" in reason for reason in draft["dropped"][0]["reasons"])
