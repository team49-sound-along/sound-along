"""Generator Lambda: raw passage JSON in S3 -> MP3 + timing JSON in S3, job and passage items in DynamoDB."""
from __future__ import annotations

import _bootstrap  # noqa: F401  (must come before synth imports)

import gzip
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from asr_words import decode_audio, transcribe
from clients import Clients, create_clients
from dynamo import JobTracker, list_passage_items, now_iso, put_passage_summary
from engine import SAMPLE_RATE
from engines import create_engine
from fingerprint import fingerprint
from flow import Variant, run_flow
from mp3 import encode_mp3, resolve_kbps
from tokenizer import tokenize_html
from summary import index_entry, passage_summary
from translate import translate_passage
from translate_cards import translate_cards
from translate_flow import build_translated_passage, link, other_language, should_translate

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

FRIENDLY_ERROR = "We could not generate audio for this text. Try shorter text or remove unusual symbols."
Encoder = Callable[[np.ndarray, int, int], bytes]  # (audio, sample_rate, kbps) -> mp3 bytes


def engine_for(passage: dict[str, Any]) -> Any:
    """Build the engine from THIS job's stored settings and pronunciation fixes (nothing is baked into the image)."""
    return create_engine(
        settings=passage.get("settings"), respellings=passage.get("pronunciations"), language=passage.get("language") or "en"
    )


@dataclass(frozen=True)
class Dependencies:
    clients: Clients
    engine_factory: Callable[[dict[str, Any]], Any] = engine_for
    encoder: Encoder = encode_mp3
    transcribe_fn: Callable[..., Any] = transcribe
    decode_fn: Callable[..., Any] = decode_audio
    enrich_fn: Callable[[dict[str, Any]], Any] = lambda passage: None  # production turns this on in handler(); unit tests never touch the network
    # Translation (a second invocation, see process_translation). None means "not configured": the step reports skipped and does nothing.
    translate_model: Optional[Callable[[str, str], Callable[[list[str]], list[str]]]] = None
    names_for: Callable[[str], Callable[[str], list[str]]] = lambda language: (lambda text: [])  # place names to protect, by source language
    localize_fn: Optional[Callable[[list[str], str, str], dict[str, str]]] = None


def _read_raw(clients: Clients, raw_key: str) -> dict[str, Any]:
    body = clients.s3.get_object(Bucket=clients.bucket, Key=raw_key)["Body"].read()
    return json.loads(body)


def _put(clients: Clients, key: str, body: bytes, content_type: str, gzipped: bool = False, cache_control: str | None = None) -> None:
    """ReadWorks' guide: large word-level timing "can live in S3 in zipped form". Gzipped objects carry
    Content-Encoding, so a browser's fetch() decompresses them without any client code."""
    if gzipped:
        clients.s3.put_object(Bucket=clients.bucket, Key=key, Body=gzip.compress(body, mtime=0), ContentType=content_type, ContentEncoding="gzip")
    else:
        extra = {"CacheControl": cache_control} if cache_control else {}
        clients.s3.put_object(Bucket=clients.bucket, Key=key, Body=body, ContentType=content_type, **extra)


IMMUTABLE = "public, max-age=31536000, immutable"  # picture file names carry a content hash, so they can be cached for a year


def live_enrichment(passage: dict[str, Any]) -> Any:
    """Place cards and pictures for a teacher-generated passage (see enrich_places.py). Never raises."""
    from enrich_places import enrich_places, ner_places
    from word_pictures import word_picture_cards

    return enrich_places(passage, ner=ner_places, words=word_picture_cards)


def _cards_reviewed(clients: Clients, passage_id: str) -> bool:
    try:
        body = clients.s3.get_object(Bucket=clients.bucket, Key=f"data/{passage_id}.cards.json")["Body"].read()
        return json.loads(body).get("reviewed") is True
    except Exception:  # noqa: BLE001  (no cards yet is the normal case)
        return False


def _publish_cards(deps: "Dependencies", passage_id: str, passage: dict[str, Any]) -> None:
    """Place cards and pictures next to the audio. Best effort: a failure here must never fail a job whose audio is already published."""
    try:
        if _cards_reviewed(deps.clients, passage_id):
            return  # a person already reviewed these cards; never replace them
        enriched = deps.enrich_fn({**passage, "uuid": passage_id})
        if enriched is None:
            return
        for name, data in enriched.images.items():
            _put(deps.clients, f"data/{name}", data, "image/png" if name.endswith(".png") else "image/jpeg", cache_control=IMMUTABLE)
        _put(deps.clients, f"data/{passage_id}.cards.json", json.dumps(enriched.cards, ensure_ascii=False).encode("utf-8"), "application/json")
    except Exception:  # noqa: BLE001
        LOG.exception("place cards skipped for %s", passage_id)


def _publish(deps: Dependencies, variant: Variant, kbps: int, source: str, workdir: Path) -> dict[str, Any]:
    mp3_path = workdir / f"{variant.id}.mp3"
    mp3_path.write_bytes(deps.encoder(variant.audio, SAMPLE_RATE, kbps))
    timing_path = workdir / f"{variant.id}.timing.json"
    timing_path.write_text(json.dumps(variant.timing, ensure_ascii=False), encoding="utf-8")
    _put(deps.clients, f"data/{variant.id}.mp3", mp3_path.read_bytes(), "audio/mpeg")
    _put(deps.clients, f"data/{variant.id}.timing.json", timing_path.read_bytes(), "application/json", gzipped=True)
    summary = passage_summary(variant.timing, now_iso(), source)
    put_passage_summary(deps.clients.table, summary)
    return summary


def _json_default(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _write_index(clients: Clients) -> None:
    """Publish data/index.json (newest first): the frontend reads this document instead of calling the API."""
    entries = sorted((index_entry(i) for i in list_passage_items(clients.table)), key=lambda e: e.get("createdAt", ""), reverse=True)
    body = json.dumps(entries, ensure_ascii=False, default=_json_default).encode("utf-8")
    _put(clients, "data/index.json", body, "application/json", gzipped=True)


def _fetch_recording(clients: Clients, key: str, workdir: Path) -> str:
    target = workdir / "recording.audio"
    target.write_bytes(clients.s3.get_object(Bucket=clients.bucket, Key=key)["Body"].read())
    return str(target)


def _previous_timing(clients: Clients, passage_id: str) -> dict[str, Any] | None:
    """The timing document already published for this passage, or None (first run)."""
    try:
        body = clients.s3.get_object(Bucket=clients.bucket, Key=f"data/{passage_id}.timing.json")["Body"].read()
        return json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)
    except Exception:  # noqa: BLE001  (missing object, not-yet-readable object: both mean "generate")
        return None


def _run(event: dict[str, Any], deps: Dependencies, tracker: JobTracker) -> dict[str, Any]:
    passage_id = event["passageId"]
    raw = _read_raw(deps.clients, event["rawKey"])
    passage = {**raw, "uuid": passage_id, "title": raw.get("title") or event.get("title")}
    if event.get("humanPassageId") and not passage.get("humanPassageId"):
        passage = {**passage, "humanPassageId": event["humanPassageId"]}
    recording_key = (passage.get("recording") or {}).get("key")
    kbps = resolve_kbps((passage.get("settings") or {}).get("mp3Kbps"))
    source = passage.get("source") or "generated"
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        workdir = Path(tmp)
        recording_path = _fetch_recording(deps.clients, recording_key, workdir) if recording_key else None
        previous = None if passage.get("force") else _previous_timing(deps.clients, passage_id)
        if previous and previous.get("generatedWith", {}).get("hash") == fingerprint(passage, recording_path):
            LOG.info("unchanged input for %s: skipping generation", passage_id)
            tracker.step("publish")
            return previous["metrics"]
        result = run_flow(
            passage, deps.engine_factory(passage), tracker.step,
            recording_path=recording_path, transcribe_fn=deps.transcribe_fn, decode_fn=deps.decode_fn,
        )
        tracker.step("publish")
        _publish(deps, result.ai, kbps, source, workdir)
        if result.human:
            _publish(deps, result.human, kbps, source, workdir)
        _put(deps.clients, f"data/{result.ai.id}.soundalong.json", json.dumps(result.soundalong, ensure_ascii=False).encode("utf-8"), "application/json")
        _publish_cards(deps, passage_id, {**passage, "source": source})
        _write_index(deps.clients)
    return result.ai.timing["metrics"]


def _get_json(clients: Clients, key: str) -> dict[str, Any] | None:
    """A JSON object from S3 (gzipped or plain), or None when it does not exist."""
    try:
        body = clients.s3.get_object(Bucket=clients.bucket, Key=key)["Body"].read()
        return json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)
    except Exception:  # noqa: BLE001
        return None


def _language_of(deps: Dependencies, event: dict[str, Any]) -> str:
    raw = _get_json(deps.clients, event.get("rawKey") or f"raw/{event['passageId']}.json") or {}
    return raw.get("language") or "en"


def process(event: dict[str, Any], deps: Dependencies) -> dict[str, Any]:
    """Never raises: failures are logged and recorded on the job item."""
    job_id = event.get("jobId", "")
    tracker = JobTracker(deps.clients.table, job_id, event.get("title", ""))
    try:
        tracker.start()
        metrics = _run(event, deps, tracker)
        tracker.done(event["passageId"], metrics)
        # `language` lets the state machine decide what follows: questions are English-only, translation goes the other way.
        return {"status": "done", "jobId": job_id, "passageId": event["passageId"], "language": _language_of(deps, event)}
    except Exception:
        LOG.exception("generation failed for job %s", job_id)
        _mark_failed(tracker, job_id)
        return {"status": "failed", "jobId": job_id}


def _translate_cards_to_s3(deps: Dependencies, pid: str, tid: str, target_timing: dict[str, Any], model: Callable[[list[str]], list[str]],
                           lang: str, source_lang: str, localized: dict[str, str]) -> None:
    """Translated place and word cards with their pictures, uploaded next to the translated audio. Best effort."""
    try:
        doc = _get_json(deps.clients, f"data/{pid}.cards.json")
        if not doc:
            return
        files: dict[str, bytes] = {}
        for card in [*(doc.get("words") or {}).values(), *(doc.get("places") or {}).values()]:
            url = str(card.get("imageUrl") or "")
            if url.startswith("/data/") and url[6:] not in files:
                try:
                    files[url[6:]] = deps.clients.s3.get_object(Bucket=deps.clients.bucket, Key=f"data/{url[6:]}")["Body"].read()
                except Exception:  # noqa: BLE001 (a missing picture just means no picture)
                    pass
        cards, images = translate_cards(doc, [w["text"] for w in target_timing["words"]], model, pid, tid, files, lang, localized=localized, source_lang=source_lang)
        for name, data in images.items():
            _put(deps.clients, f"data/{name}", data, "image/png" if name.endswith(".png") else "image/jpeg", cache_control=IMMUTABLE)
        _put(deps.clients, f"data/{tid}.cards.json", json.dumps(cards, ensure_ascii=False).encode("utf-8"), "application/json")
    except Exception:  # noqa: BLE001
        LOG.exception("translated cards skipped for %s", tid)


def _relink_source(deps: Dependencies, sid: str, doc: dict[str, Any]) -> None:
    """Upload a source timing document that now carries the translation link, and refresh its PASSAGE summary (keeping its creation time)."""
    _put(deps.clients, f"data/{sid}.timing.json", json.dumps(doc, ensure_ascii=False).encode("utf-8"), "application/json", gzipped=True)
    existing = next((i for i in list_passage_items(deps.clients.table) if i.get("id") == sid or i.get("sk") == sid), {})
    put_passage_summary(deps.clients.table, passage_summary(doc, existing.get("createdAt") or now_iso(), existing.get("source") or "generated"))


def process_translation(event: dict[str, Any], deps: Dependencies) -> dict[str, Any]:
    """The other-language version of a passage, as its own linked passage. Runs as a SECOND invocation after generation (own timeout, own failure).

    Never raises. The translated passage is published first and the source documents are linked last, so a failure never leaves a link to a
    passage that does not exist."""
    pid, job_id = event.get("passageId", ""), event.get("jobId", "")
    out = {"jobId": job_id, "passageId": pid}
    try:
        if deps.translate_model is None:
            return {**out, "status": "skipped", "reason": "translation is not configured"}
        raw = _read_raw(deps.clients, event.get("rawKey") or f"raw/{pid}.json")
        passage = {**raw, "uuid": pid, "language": raw.get("language") or "en", "source": raw.get("source") or "generated"}
        if not should_translate(passage):
            return {**out, "status": "skipped", "reason": "not for this passage"}
        source_lang = passage["language"]
        lang = other_language(source_lang)
        model = deps.translate_model(source_lang, lang)
        localize = (lambda names: deps.localize_fn(names, source_lang, lang)) if deps.localize_fn else None
        translated = translate_passage(passage, model, deps.names_for(source_lang), localize=localize)
        job = build_translated_passage(passage, lang, translated)
        tid = job["uuid"]
        kbps = resolve_kbps((passage.get("settings") or {}).get("mp3Kbps"))
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            result = run_flow(job, deps.engine_factory(job), lambda step: None, transcribe_fn=deps.transcribe_fn, decode_fn=deps.decode_fn)
            n_target = len({w["sentence"] for w in result.ai.timing["words"]})
            _, linked = link({"id": pid}, result.ai.timing, lang, tid, source_lang, translated, n_target)
            _publish(deps, Variant(tid, result.ai.audio, linked), kbps, passage["source"], Path(tmp))
            _put(deps.clients, f"data/{tid}.soundalong.json", json.dumps(result.soundalong, ensure_ascii=False).encode("utf-8"), "application/json")
        _translate_cards_to_s3(deps, pid, tid, linked, model, lang, source_lang, translated.localized)
        primary = _get_json(deps.clients, f"data/{pid}.timing.json") or {}
        for sid in [pid, *([primary["pairId"]] if primary.get("pairId") else [])]:  # the Library opens either variant, so both get the link
            doc = _get_json(deps.clients, f"data/{sid}.timing.json")
            if doc:
                _relink_source(deps, sid, link(doc, linked, lang, tid, source_lang, translated, n_target)[0])
        _write_index(deps.clients)
        return {**out, "status": "done", "translatedId": tid}
    except Exception:
        LOG.exception("translation failed for %s", pid)
        return {**out, "status": "failed"}


def _mark_failed(tracker: JobTracker, job_id: str) -> None:
    try:
        tracker.failed(FRIENDLY_ERROR)
    except Exception:
        LOG.exception("could not record failure for job %s", job_id)


def _load_translator(source: str, target: str) -> Callable[[list[str]], list[str]]:
    from translate import load_model

    return load_model(source, target)


def _names_for(language: str) -> Callable[[str], list[str]]:
    """Place names to protect during translation: spaCy places for English, capitalised names otherwise."""
    from enrich_places import ner_places, place_candidates

    if language == "en":
        return ner_places
    return lambda text: place_candidates(tokenize_html("<p>" + text + "</p>"))


def _localize(names: list[str], source: str, target: str) -> dict[str, str]:
    from translate_flow import localize_with_wikipedia

    return localize_with_wikipedia(names, source, target)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        clients = create_clients()
    except Exception:
        LOG.exception("generator configuration error")
        return {"status": "failed", "jobId": event.get("jobId", "")}
    if event.get("mode") == "translate":
        return process_translation(event, Dependencies(clients=clients, translate_model=_load_translator, names_for=_names_for, localize_fn=_localize))
    return process(event, Dependencies(clients=clients, enrich_fn=live_enrichment))
