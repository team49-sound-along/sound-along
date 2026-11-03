"""Comparing the judge's decisions with human labels."""
from qg_eval import compare

LABELS = [
    {"passageId": "p", "question": "A?", "verdict": "good", "failed": []},
    {"passageId": "p", "question": "B?", "verdict": "good", "failed": []},
    {"passageId": "p", "question": "C?", "verdict": "fixable", "failed": ["grounded"]},
    {"passageId": "p", "question": "D?", "verdict": "reject", "failed": ["noFalsePremise"]},
    {"passageId": "p", "question": "E?", "verdict": "reject", "failed": ["oneCorrectAnswer"]},
]


def outcome(passed, failed=(), unknown=()):
    return {"passed": passed, "failed": list(failed), "unknown": list(unknown), "reasons": {}}


JUDGED = {
    ("p", "A?"): outcome(True),
    ("p", "B?"): outcome(False, ["oneCorrectAnswer"]),  # a good question the judge wrongly dropped
    ("p", "C?"): outcome(True),
    ("p", "D?"): outcome(False, ["noFalsePremise"]),  # caught, for the right reason
    ("p", "E?"): outcome(True),  # a bad question the judge let through
}


def test_confusion_counts_by_label():
    report = compare(LABELS, JUDGED)
    assert report["confusion"] == {"good": {"passed": 1, "dropped": 1}, "fixable": {"passed": 1, "dropped": 0}, "reject": {"passed": 1, "dropped": 1}}


def test_the_two_costly_mistakes_are_named():
    report = compare(LABELS, JUDGED)
    assert [m["question"] for m in report["badKept"]] == ["E?"]
    assert [m["question"] for m in report["goodDropped"]] == ["B?"]


def test_a_catch_counts_as_right_only_when_the_failed_criterion_matches():
    report = compare(LABELS, JUDGED)
    assert report["rightReason"] == {"D?": True}


def test_unjudged_questions_and_unlabelled_ones_are_reported_not_hidden():
    report = compare(LABELS + [{"passageId": "p", "question": "F?", "verdict": "good", "failed": []}], JUDGED)
    assert report["missingJudgement"] == ["F?"]
    assert compare(LABELS, {**JUDGED, ("p", "Z?"): outcome(True)})["unlabelled"] == ["Z?"]
