"""Word timing for EXISTING human narration: align the known passage words to an ASR transcript with word times.

The passage text is the source of truth for what is displayed; the audio only supplies times. Extra spoken words
(a read-aloud title, ad-libs) are ignored. Words the recognizer did not match are interpolated and flagged
``aligned=False`` so quality reporting stays honest.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, Sequence

from asr_words import Heard, expand_spoken_numbers, norm

LEADING_STEP_S = 0.3  # spacing used when words precede the first matched word or follow the last one


@dataclass(frozen=True)
class AlignedWord:
    start_s: float
    end_s: float
    aligned: bool


def align_words(display: Sequence[str], heard: Sequence[Heard], duration_s: Optional[float] = None) -> list[AlignedWord]:
    """One AlignedWord per display word, in order, with non-decreasing starts. With `duration_s` (the length of the audio) no word runs past the end."""
    heard = expand_spoken_numbers(list(heard), display)
    shown = [(i, norm(w)) for i, w in enumerate(display) if norm(w)]
    spoken = [(j, norm(h.text)) for j, h in enumerate(heard) if norm(h.text)]
    times: dict[int, tuple[float, float, bool]] = {}

    matcher = SequenceMatcher(a=[n for _, n in shown], b=[n for _, n in spoken], autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        paired = tag == "equal" or (tag == "replace" and (a1 - a0) == (b1 - b0))
        if not paired:
            continue  # deletions are interpolated; insertions (extra spoken words) are ignored
        for k in range(a1 - a0):
            h = heard[spoken[b0 + k][0]]
            times[shown[a0 + k][0]] = (h.start_s, h.end_s, tag == "equal")

    return _fit_to_audio(_fill_gaps(len(display), times), duration_s)


def _fit_to_audio(words: list[AlignedWord], duration_s: Optional[float]) -> list[AlignedWord]:
    """Trailing words the recognizer missed are given fixed steps after the last matched word; a long tail can end up beyond the audio. Squeeze those
    estimated words evenly into the time that is left."""
    if duration_s is None or not words or words[-1].end_s <= duration_s:
        return words
    last_real = max((i for i, w in enumerate(words) if w.aligned), default=-1)
    tail = words[last_real + 1:]
    start = min(words[last_real].end_s if last_real >= 0 else 0.0, duration_s)
    step = (duration_s - start) / max(len(tail), 1)
    squeezed = [AlignedWord(start + k * step, start + (k + 1) * step, False) for k in range(len(tail))]
    head = [AlignedWord(w.start_s, min(w.end_s, duration_s), w.aligned) for w in words[: last_real + 1]]
    return head + squeezed


def _fill_gaps(count: int, times: dict[int, tuple[float, float, bool]]) -> list[AlignedWord]:
    anchors = sorted(times)
    out: list[AlignedWord] = []
    clock = 0.0
    for i in range(count):
        if i in times:
            start, end, exact = times[i]
        else:
            before = max((a for a in anchors if a < i), default=None)
            after = min((a for a in anchors if a > i), default=None)
            if before is not None and after is not None:
                span = times[after][0] - times[before][1]
                share = (i - before) / (after - before)
                start = times[before][1] + span * share
            elif after is not None:
                start = max(0.0, times[after][0] - LEADING_STEP_S * (after - i))
            elif before is not None:
                start = times[before][1] + LEADING_STEP_S * (i - before)
            else:
                start = clock
            end, exact = start + 0.2, False
        start = max(start, clock)
        end = max(end, start)
        out.append(AlignedWord(start, end, exact))
        clock = start
    # A word never ends after the next one starts. Estimated words get a fixed 0.2 s, which overlaps the next word when many are squeezed into
    # a short stretch (a tongue-twister the recognizer could not align); overlapping words made the highlight jump back and forth.
    return [AlignedWord(w.start_s, max(w.start_s, min(w.end_s, nxt.start_s)), w.aligned) for w, nxt in zip(out, out[1:])] + out[-1:]
