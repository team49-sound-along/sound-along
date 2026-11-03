"""Cards for a translated passage, so everything connected to the text still works after the language switch.

* Words: a card is keyed by the word that is REALLY in the translated text (the key the reader looks up). It comes from a ReadWorks translation of
  a card's word (`spanish`), or from a machine translation of the headword, and only if that word appears in the text. It shows the original
  headword (`translation: {lang, words}`). Definitions are machine translated.
* Places: the localised name (Gran Bretaña) when it appears in the text; the summary is machine translated; the PICTURE is reused (copied under the
  new passage's id) with its alt text and credit translated.
Nothing here needs the network. The result is marked machine translated and unreviewed.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional, Sequence

from place_media import image_ext, image_size, target_name

TranslateFn = Callable[[list[str]], list[str]]
_EDGE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)
_CREDIT_WORDS = {
    "es": (("Photo:", "Foto:"), ("Image:", "Imagen:"), ("Picture:", "Imagen:"), ("via Wikimedia Commons", "vía Wikimedia Commons")),
    "en": (("Foto:", "Photo:"), ("Imagen:", "Image:"), ("vía Wikimedia Commons", "via Wikimedia Commons")),
}
_NOTE = {"es": "traducción automática", "en": "machine translation"}


def word_key(text: str) -> str:
    """Lower case with punctuation removed from both edges; inner apostrophes stay (the same rule as the reader)."""
    return _EDGE.sub("", str(text or "")).lower()


def _trim(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    first = re.match(r"^(.+?[.!?])(\s|$)", text)
    if first and len(first.group(1)) <= limit:
        return first.group(1)
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return (cut or text[: limit - 1]) + "…"


def _credit(text: Optional[str], lang: str) -> Optional[str]:
    if text is None:
        return None
    for old, new in _CREDIT_WORDS.get(lang, ()):
        text = text.replace(old, new)
    return text


def translate_cards(
    source_cards: Mapping[str, Any], target_tokens: Sequence[str], model: TranslateFn, source_id: str, new_id: str, files: Mapping[str, bytes],
    target_lang: str, localized: Optional[Mapping[str, str]] = None, source_lang: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """(cards document, picture files) for the translated passage. `files` holds the source passage's picture files by name."""
    source_lang = source_lang or ("en" if target_lang == "es" else "es")
    localized = localized or {}
    present = [word_key(t) for t in target_tokens]
    keys = set(present)

    def appears(phrase: str) -> bool:
        parts = [word_key(p) for p in phrase.split()]
        return bool(parts) and any(present[i:i + len(parts)] == parts for i in range(len(present) - len(parts) + 1))

    words_in = source_cards.get("words") or {}
    places_in = source_cards.get("places") or {}
    # one batch of machine translation for everything that needs it
    wanted: list[str] = []
    for w, c in words_in.items():
        wanted += [w, c.get("definition") or "", c.get("imageAlt") or ""]
    for p in places_in.values():
        wanted += [p.get("summary") or "", p.get("imageAlt") or ""]
    unique = [t for t in dict.fromkeys(wanted) if t.strip()]
    done = dict(zip(unique, model(unique))) if unique else {}
    mt = lambda t: done.get(t, "") if t else ""  # noqa: E731

    images: dict[str, bytes] = {}

    def copy_picture(card: Mapping[str, Any], key: str, kind: str) -> dict[str, Any]:
        out = {"imageUrl": None, "imageAlt": None, "imageCredit": None, "imageWidth": None, "imageHeight": None}
        data = files.get(str(card.get("imageUrl") or "").removeprefix("/data/"))
        if data is None or image_ext(data) is None:
            return out
        name = target_name(new_id, key, data, kind=kind)
        images[name] = data
        width, height = image_size(data) or (None, None)
        return {"imageUrl": f"/data/{name}", "imageAlt": mt(card.get("imageAlt") or "") or None, "imageCredit": _credit(card.get("imageCredit"), target_lang),
                "imageWidth": width, "imageHeight": height}

    words: dict[str, dict[str, Any]] = {}
    for source_word, card in words_in.items():
        candidates = [*(card.get("spanish") or []), mt(source_word)]
        chosen = next((word_key(c) for c in candidates if c and " " not in c.strip() and word_key(c) in keys), None)
        if not chosen or chosen in words:
            continue
        words[chosen] = {
            "word": chosen, "syllables": None, "ipa": None, "partOfSpeech": card.get("partOfSpeech") or "noun",
            "definition": _trim(mt(card.get("definition") or ""), 140), "example": None, "spanish": [],
            "translation": {"lang": source_lang, "words": [source_word]}, **copy_picture(card, chosen, "word"),
        }

    places: dict[str, dict[str, Any]] = {}
    for name, card in places_in.items():
        local = localized.get(name, name)
        if not appears(local):
            continue
        places[local] = {
            "name": local, "summary": _trim(mt(card.get("summary") or ""), 160), "attribution": f"{card.get('attribution') or 'Wikipedia, CC BY-SA'} ({_NOTE[target_lang]})",
            **copy_picture(card, local, "place"),
        }
    return {"words": words, "places": places, "reviewed": False, "source": "translated", "machineTranslated": True}, images
