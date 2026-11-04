"""Who does "su" belong to? Spanish su/sus means his, her, their (or your) and a sentence-level translator cannot tell which: it only sees one sentence.
This looks at the sentences before it. A tiny English language model (SmolLM2-135M, Apache-2.0) is asked how much the earlier text supports "his", "her" or
"their" at the place where the pronoun stands, compared with how likely each is without that text. The translator's own choice is changed only when the
evidence is clear (a margin), so a correct pronoun is not disturbed. Measured on 74 labelled cases: 97% right on its own, and with the margin below it fixed
89% of wrong pronouns and broke none of the correct ones.

Used only for Spanish to English, only for a sentence that has su/sus, and only when the translation has the same number of possessive slots. Off (no change
at all) when the model is not installed or POSSESSIVE_FIX=off."""
from __future__ import annotations

import logging
import os
import re
from typing import Callable, Optional, Sequence

LOG = logging.getLogger(__name__)
OPTIONS = ("his", "her", "their")
MARGIN = 0.6  # nats: how much better the best pronoun must be than the translator's before it is replaced
CONTEXT_SENTENCES = 3
MODEL_REPO, MODEL_REVISION = "HuggingFaceTB/SmolLM2-135M", "93efa2f097d58c2a74874c7e644dbc9b0cee75a2"

_SU = re.compile(r"\bsus?\b", re.I)
_SLOT = re.compile(r"\b(his|her|their)\b", re.I)
# "her" followed by one of these is the object pronoun ("gave her the book"), not the possessive ("her book").
_NOT_A_NOUN_PHRASE = frozenset("the a an to in on at for with and but or that this these those it him them me us you there up down out off about from as so if when because by into over back home away what who which than then too also very not no".split())


def su_count(source: str) -> int:
    return len(_SU.findall(source))


def possessive_slots(sentence: str) -> list[tuple[int, int, str]]:
    """(start, end, word) of each his/her/their that is a possessive (followed by a noun phrase), left to right."""
    slots = []
    for m in _SLOT.finditer(sentence):
        rest = sentence[m.end():].lstrip()
        nxt = re.match(r"[A-Za-z][A-Za-z'’-]*", rest)
        if not nxt or nxt.group(0).lower() in _NOT_A_NOUN_PHRASE:
            continue
        slots.append((m.start(), m.end(), m.group(0)))
    return slots


def _matching_case(word: str, original: str) -> str:
    return word.capitalize() if original[:1].isupper() else word


def resolve_possessives(sources: Sequence[str], outputs: Sequence[str], scorer: Optional[Callable[[str, str], dict[str, float]]], margin: float = MARGIN) -> list[str]:
    """New list of translations with the possessive pronouns chosen from context. `scorer(context, before)` returns, for each of OPTIONS, how much
    `context` supports that word right after `before` (higher is better). With no scorer the translations are returned unchanged."""
    if scorer is None:
        return list(outputs)
    done: list[str] = []
    for source, output in zip(sources, outputs):
        slots = possessive_slots(output)
        if su_count(source) == 0 or not slots or len(slots) != su_count(source):
            done.append(output)
            continue
        context = " ".join(done[-CONTEXT_SENTENCES:])
        if not context:
            done.append(output)  # nothing before it to learn from
            continue
        text = output
        for start, end, word in reversed(slots):  # right to left, so earlier positions stay valid
            try:
                scores = scorer(context, text[:start].rstrip())
            except Exception as err:  # noqa: BLE001 (a broken scorer must never break a translation)
                LOG.warning("possessive check skipped: %s", err)
                break
            current = word.lower()
            best = max(scores, key=scores.get)
            if best != current and scores[best] - scores.get(current, float("-inf")) >= margin:
                text = text[:start] + _matching_case(best, word) + text[end:]
        done.append(text)
    return done


class PronounScorer:
    """Scores his/her/their with SmolLM2-135M. The first call loads the model (from POSSESSIVE_LM_DIR in the image, otherwise the pinned revision)."""

    def __init__(self) -> None:
        self._model = self._tok = None

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        where = os.environ.get("POSSESSIVE_LM_DIR")
        kwargs = {"local_files_only": True} if where else {"revision": MODEL_REVISION}
        where = where or MODEL_REPO
        self._tok = AutoTokenizer.from_pretrained(where, **kwargs)
        self._model = AutoModelForCausalLM.from_pretrained(where, dtype=torch.float32, **kwargs).eval()

    def _logp(self, prefix: str, candidate: str) -> float:
        import torch

        cand = self._tok(candidate, return_tensors="pt", add_special_tokens=False).input_ids
        if prefix:
            pre = self._tok(prefix, return_tensors="pt").input_ids
            ids, start = torch.cat([pre, cand], 1), pre.shape[1]
        else:
            bos = self._tok.bos_token_id if self._tok.bos_token_id is not None else self._tok.eos_token_id
            ids, start = torch.cat([torch.tensor([[bos]]), cand], 1), 1
        with torch.no_grad():
            lp = torch.log_softmax(self._model(input_ids=ids).logits[0, :-1], -1)
        return float(lp.gather(1, ids[0, 1:, None])[start - 1:, 0].sum())

    def __call__(self, context: str, before: str) -> dict[str, float]:
        if self._model is None:
            self._load()
        at_start = not before.strip()
        scores = {}
        for option in OPTIONS:
            cand = " " + (option.capitalize() if at_start else option)
            scores[option] = self._logp(f"{context} {before}".rstrip(), cand) - self._logp(before, cand)
        return scores


def load_scorer() -> Optional[PronounScorer]:
    """The scorer, or None when the check is switched off (POSSESSIVE_FIX=off) or the model files are not there."""
    if os.environ.get("POSSESSIVE_FIX", "on").strip().lower() in ("off", "0", "false", "no"):
        return None
    where = os.environ.get("POSSESSIVE_LM_DIR")
    if where and not os.path.isdir(where):
        LOG.warning("possessive check off: %s not found", where)
        return None
    return PronounScorer()
