"""Publish a translation as its OWN passage (own id, audio, timing, phrase breaks), linked both ways to the source.

The link carries a sentence map, so the reader keeps its place when you switch language:
  source timing   translations: {"es": {"id": <translated id>, "sentenceMap": [[0], [1, 2], ...]}}   (source sentence -> target sentences)
  translated      translationOf: {"id", "lang", "sentenceMap": [0, 1, 1, ...]}, machineTranslated: true  (target sentence -> source sentence)
Every variant of the source (the read-aloud voice AND a human narration) gets the link, because the Library opens either one.
Best effort: with safe=True a failure returns None and leaves no dangling link.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from translate import Translated, load_model, translate_passage
from translate_cards import translate_cards

LOG = logging.getLogger(__name__)
NAMESPACE = uuid.UUID("5b1f6d2e-8c1a-4c3e-9a47-2f0e6a1d7b90")
RunFn = Callable[[dict[str, Any], Path], Any]


def translated_id(source_id: str, lang: str) -> str:
    """A stable id for the translation of a passage into `lang` (so regenerating never creates a duplicate)."""
    return str(uuid.uuid5(NAMESPACE, f"{source_id}:{lang}"))


def other_language(lang: Optional[str]) -> str:
    return "en" if lang == "es" else "es"


def invert_map(sentence_map: Sequence[Sequence[int]], n_target: int) -> list[int]:
    """Target sentence number -> the source sentence it came from."""
    out: list[Optional[int]] = [None] * n_target
    for source, targets in enumerate(sentence_map):
        for t in targets:
            if 0 <= t < n_target:
                out[t] = source
    if any(v is None for v in out):
        raise ValueError("the sentence map does not cover every translated sentence")
    return [int(v) for v in out]  # type: ignore[arg-type]


def build_translated_passage(passage: dict[str, Any], lang: str, translated: Translated) -> dict[str, Any]:
    """The job input for the translated passage: Spanish or English narration, the same settings, and no English pronunciation fixes."""
    return {
        "uuid": translated_id(passage["uuid"], lang), "title": translated.title or passage.get("title"), "content": translated.content_html,
        "language": lang, "source": passage.get("source") or "generated", "settings": dict(passage.get("settings") or {}), "pronunciations": {},
    }


def link(source_timing: dict[str, Any], translated_timing: dict[str, Any], lang: str, tid: str, source_lang: str, translated: Translated, n_target: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """New copies of both timing documents with the links added. The inputs are not changed."""
    new_source = {**source_timing, "translations": {**(source_timing.get("translations") or {}), lang: {"id": tid, "sentenceMap": [list(g) for g in translated.sentence_map]}}}
    new_target = {**translated_timing, "machineTranslated": True,
                  "translationOf": {"id": source_timing["id"], "lang": source_lang, "sentenceMap": invert_map(translated.sentence_map, n_target)}}
    return new_source, new_target


def localize_with_wikipedia(names: Sequence[str], source_lang: str, target_lang: str, http_get: Optional[Callable[..., Any]] = None) -> dict[str, str]:
    """Each place's name in the target language from Wikipedia's language links (Great Britain -> Gran Bretaña). Qualifiers such as "(Estados Unidos)"
    are dropped. Offline or any failure gives an empty result, so the original names are kept."""
    try:
        import urllib.parse

        from enrich_places import fetch

        get = http_get or fetch
        url = (f"https://{source_lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "format": "json", "redirects": "1", "prop": "langlinks", "lllang": target_lang, "lllimit": "max", "titles": "|".join(names)}))
        reply = get(url)
        pages = reply["query"]["pages"].values()
        titles = {p.get("title"): next((l["*"] for l in p.get("langlinks", []) if l.get("lang") == target_lang), None) for p in pages}
        out = {}
        for name in names:
            local = titles.get(name)
            if local:
                out[name] = local.split(" (")[0].strip()
        return out
    except Exception as err:  # noqa: BLE001
        LOG.info("place names not localised: %s", err)
        return {}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cards(data_dir: Path, primary: str, tid: str, target: dict[str, Any], model: Callable[[list[str]], list[str]], lang: str, source_lang: str, translated: Translated) -> None:
    """Translated place and word cards (with the pictures copied under the new id), when the source passage has cards. Best effort."""
    source_path = data_dir / f"{primary}.cards.json"
    if not source_path.exists():
        return
    try:
        files = {p.name: p.read_bytes() for p in data_dir.glob(f"{primary}.*") if ".place-" in p.name or ".word-" in p.name}
        doc, images = translate_cards(_read(source_path), [w["text"] for w in target.get("words", [])], model, primary, tid, files, lang,
                                      localized=translated.localized, source_lang=source_lang)
        for name, data in images.items():
            (data_dir / name).write_bytes(data)
        (data_dir / f"{tid}.cards.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as err:  # noqa: BLE001 (cards are a bonus: the translated passage itself is already published)
        LOG.warning("translated cards skipped for %s: %s", tid, err)


def publish_translation(
    passage: dict[str, Any], data_dir: Path, lang: str, translated: Optional[Translated] = None, run_fn: Optional[RunFn] = None,
    names_fn: Optional[Callable[[str], list[str]]] = None, source_ids: Optional[Sequence[str]] = None, safe: bool = False,
    model: Optional[Callable[[list[str]], list[str]]] = None, localize: Optional[Callable[[list[str]], Any]] = None,
) -> Optional[str]:
    """Translate (unless `translated` is given), generate the translated passage with the normal flow, then link every source variant to it.
    Returns the translated passage's id. With safe=True never raises and returns None on failure."""
    try:
        source_lang = passage.get("language") or "en"
        if translated is None:
            if names_fn is None:
                from enrich_places import ner_places, place_candidates  # noqa: F401
                from pipeline import tokenize_html

                names_fn = ner_places if source_lang == "en" else (lambda text: place_candidates(tokenize_html("<p>" + text + "</p>")))
            model = model or load_model(source_lang, lang)
            localize = localize or (lambda names: localize_with_wikipedia(names, source_lang, lang))
            translated = translate_passage(passage, model, names_fn, localize=localize)
        if run_fn is None:
            from run_local import run as run_fn  # type: ignore[assignment]
        job = build_translated_passage(passage, lang, translated)
        run_fn(job, data_dir)  # type: ignore[misc]
        tid = job["uuid"]
        target_path = data_dir / f"{tid}.timing.json"
        target = _read(target_path)
        n_target = len({w["sentence"] for w in target.get("words", [])})
        primary = passage["uuid"]
        ids = list(source_ids or [primary])
        _, target = link({"id": primary}, target, lang, tid, source_lang, translated, n_target)  # the translation points back to the PRIMARY passage
        updated: dict[Path, dict[str, Any]] = {}
        for sid in ids:
            path = data_dir / f"{sid}.timing.json"
            if path.exists():
                updated[path], _ = link(_read(path), target, lang, tid, source_lang, translated, n_target)  # every variant gets the forward link
        target_path.write_text(json.dumps(target, ensure_ascii=False), encoding="utf-8")
        for path, doc in updated.items():
            path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        if model is not None:
            _write_cards(data_dir, primary, tid, target, model, lang, source_lang, translated)
        return tid
    except Exception as err:  # noqa: BLE001
        if not safe:
            raise
        LOG.warning("translation skipped for %s: %s", passage.get("uuid"), err)
        return None
