"""Shared test fixtures. Every test in this folder runs with no network and no model."""
import pytest

SENTENCES = [
    "A city park is a fun place to relax.",
    "People can play on the grass.",
    "In Atlanta, Georgia, there is a big park called Piedmont Park.",
    "Many families visit it on weekends.",
]


def make_timing(sentences=SENTENCES, passage_id="p-1", title="Park Day"):
    words, index = [], 0
    for number, sentence in enumerate(sentences):
        for text in sentence.split(" "):
            words.append({"i": index, "text": text, "sentence": number, "paragraph": 0, "start_ms": index * 300, "end_ms": index * 300 + 250})
            index += 1
    return {"id": passage_id, "title": title, "language": "en", "words": words}


@pytest.fixture
def timing():
    return make_timing()


@pytest.fixture
def good_raw():
    return {
        "skill": "literal",
        "question": "Where is Piedmont Park?",
        "choices": ["In Atlanta, Georgia.", "In a small town.", "Far from any city."],
        "answerIndex": 0,
        "evidenceSentence": 2,
    }


class PretendModel:
    """A fake model for pipeline tests. Its first reply is the generation; every later call answers a multiple-choice prompt
    by looking the right choice up in `truth` (question text -> right choice text), so it works whatever order the shuffle chose.
    `with_passage` / `without_passage` are "right" or "wrong"."""

    def __init__(self, generation, truth, with_passage="right", without_passage="wrong", tokens=(50, 4)):
        self.generation, self.truth = generation, truth
        self.with_passage, self.without_passage, self.tokens = with_passage, without_passage, tokens
        self.calls = []

    def complete(self, system, user, *, max_tokens=1500, temperature=0.2):
        import json

        from qg_adapters import ModelReply

        self.calls.append((system, user))
        if len(self.calls) == 1:
            return self.generation
        question = next(text for text in self.truth if text in user)
        lines = [line for line in user.splitlines() if line[:2] in ("A.", "B.", "C.", "D.")]
        right = next(line[0] for line in lines if line[3:].strip() == self.truth[question])
        mode = self.with_passage if "[0]" in user else self.without_passage
        letter = right if mode == "right" else next(line[0] for line in lines if line[0] != right)
        return ModelReply(json.dumps({"answer": letter}), *self.tokens)
