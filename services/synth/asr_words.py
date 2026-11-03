"""Speech-recognition helpers shared by the quality lab, human-audio alignment and the pronunciation check.

Lives in ``synth`` because the generator Lambda image ships only ``parse`` and ``synth``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

import numpy as np

SR = 16_000
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def norm(text: str) -> str:
    """Letters and digits only, lower case, accents removed: "¡Allí!" -> "alli", "niños" -> "ninos".

    Accent-insensitive on purpose: a recognizer and a text may disagree on an accent without disagreeing on the word."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return _NON_ALNUM.sub("", "".join(c for c in decomposed if not unicodedata.combining(c)))


# Numbers can be written as digits or words ("3" vs "three"), so both forms are ignored when comparing text to speech.
NUMBER_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion first "
    "second third fourth fifth sixth seventh eighth ninth tenth".split()
)


def is_number(text: str) -> bool:
    return any(c.isdigit() for c in text) or norm(text) in NUMBER_WORDS


@dataclass(frozen=True)
class Heard:
    text: str
    start_s: float
    end_s: float


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_DIGITS = re.compile(r"\W*(\d{1,3})\W*")


def _number_words(n: int) -> list[str]:
    """English words for 0..999 as the tokens a text would show: 21 is ONE token, "twentyone" (the text spells it "twenty-one")."""
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10] + (_ONES[n % 10] if n % 10 else "")]
    return [_ONES[n // 100], "hundred", *(_number_words(n % 100) if n % 100 else [])]


def expand_spoken_numbers(heard: list[Heard], display: Sequence[str]) -> list[Heard]:
    """A recognizer writes "twenty" as "20". When the passage spells a number out, replace that digit token with its words,
    splitting its time span evenly, so "twenty", "six million" and "one hundred" align exactly instead of being estimated.

    Only whole 0..999 digit tokens are expanded, and never when the text itself shows those digits (years such as 1767, "£60"
    already match as written). English only: the words are English.
    """
    shown = {norm(w) for w in display}
    out: list[Heard] = []
    for item in heard:
        match = _DIGITS.fullmatch(item.text)
        if not match or str(int(match.group(1))) in shown or match.group(1) in shown:
            out.append(item)
            continue
        words = _number_words(int(match.group(1)))
        step = (item.end_s - item.start_s) / len(words)
        out.extend(Heard(w, item.start_s + i * step, item.start_s + (i + 1) * step) for i, w in enumerate(words))
    return out


def decode_audio(path: str, sample_rate: int = SR) -> np.ndarray:
    """Decode any common audio file (mp3, wav, m4a, webm) to mono float32 at ``sample_rate``.

    Uses PyAV directly (it ships its own codecs, so no ffmpeg binary is needed in the Lambda image). faster-whisper's
    own decoder is avoided because it passes an option that not every PyAV version accepts.
    """
    import av

    chunks: list[np.ndarray] = []
    with av.open(path) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("The file has no audio track.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        for frame in container.decode(stream):
            chunks.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        chunks.extend(f.to_ndarray().reshape(-1) for f in (resampler.resample(None) or []))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def decode_16k(path: str) -> np.ndarray:
    return decode_audio(path, SR)


def resample_to_16k(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Linear resample of in-memory audio for recognition (accurate enough for speech recognition)."""
    if sample_rate == SR or audio.size == 0:
        return audio.astype(np.float32)
    target = int(round(len(audio) * SR / sample_rate))
    return np.interp(np.linspace(0, len(audio) - 1, target), np.arange(len(audio)), audio).astype(np.float32)


_MODELS: dict[str, object] = {}


def model_name_for(language: str) -> str:
    """English uses the small English-only model; every other language the multilingual small model."""
    return "small.en" if language == "en" else "small"


def transcribe(audio: np.ndarray, language: str = "en", model_name: str | None = None) -> list[Heard]:
    """Word-level transcript of 16 kHz mono float audio (faster-whisper, CPU, int8). Models load once per process."""
    from faster_whisper import WhisperModel

    name = model_name or model_name_for(language)
    if name not in _MODELS:
        _MODELS[name] = WhisperModel(name, device="cpu", compute_type="int8")
    segments, _ = _MODELS[name].transcribe(audio, language=language, word_timestamps=True, beam_size=5, condition_on_previous_text=False)
    return [Heard(w.word.strip(), float(w.start), float(w.end)) for seg in segments for w in (seg.words or [])]
