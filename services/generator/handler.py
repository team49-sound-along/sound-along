"""Generator Lambda: raw passage JSON in S3 -> MP3 + timing JSON in S3, job and passage items in DynamoDB."""
from __future__ import annotations

import _bootstrap  # noqa: F401  (must come before synth imports)

import gzip
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from asr_words import decode_audio, transcribe
from clients import Clients, create_clients
from dynamo import JobTracker, now_iso, put_passage_summary
from engine import SAMPLE_RATE
from engines import create_engine
from flow import Variant, run_flow
from mp3 import encode_mp3, resolve_kbps
from summary import passage_summary

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

FRIENDLY_ERROR = "We could not generate audio for this text. Try shorter text or remove unusual symbols."
Encoder = Callable[[np.ndarray, int, int], bytes]  # (audio, sample_rate, kbps) -> mp3 bytes


def engine_for(passage: dict[str, Any]) -> Any:
    """Build the engine from THIS job's stored settings and pronunciation fixes (nothing is baked into the image)."""
    return create_engine(settings=passage.get("settings"), respellings=passage.get("pronunciations"))


@dataclass(frozen=True)
class Dependencies:
    clients: Clients
    engine_factory: Callable[[dict[str, Any]], Any] = engine_for
    encoder: Encoder = encode_mp3
    transcribe_fn: Callable[..., Any] = transcribe
    decode_fn: Callable[..., Any] = decode_audio


def _read_raw(clients: Clients, raw_key: str) -> dict[str, Any]:
    body = clients.s3.get_object(Bucket=clients.bucket, Key=raw_key)["Body"].read()
    return json.loads(body)


def _put(clients: Clients, key: str, body: bytes, content_type: str, gzipped: bool = False) -> None:
    """ReadWorks' guide: large word-level timing "can live in S3 in zipped form". Gzipped objects carry
    Content-Encoding, so a browser's fetch() decompresses them without any client code."""
    if gzipped:
        clients.s3.put_object(Bucket=clients.bucket, Key=key, Body=gzip.compress(body, mtime=0), ContentType=content_type, ContentEncoding="gzip")
    else:
        clients.s3.put_object(Bucket=clients.bucket, Key=key, Body=body, ContentType=content_type)


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


def _fetch_recording(clients: Clients, key: str, workdir: Path) -> str:
    target = workdir / "recording.audio"
    target.write_bytes(clients.s3.get_object(Bucket=clients.bucket, Key=key)["Body"].read())
    return str(target)


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
        result = run_flow(
            passage, deps.engine_factory(passage), tracker.step,
            recording_path=recording_path, transcribe_fn=deps.transcribe_fn, decode_fn=deps.decode_fn,
        )
        tracker.step("publish")
        _publish(deps, result.ai, kbps, source, workdir)
        if result.human:
            _publish(deps, result.human, kbps, source, workdir)
        _put(deps.clients, f"data/{result.ai.id}.soundalong.json", json.dumps(result.soundalong, ensure_ascii=False).encode("utf-8"), "application/json")
    return result.ai.timing["metrics"]


def process(event: dict[str, Any], deps: Dependencies) -> dict[str, Any]:
    """Never raises: failures are logged and recorded on the job item."""
    job_id = event.get("jobId", "")
    tracker = JobTracker(deps.clients.table, job_id, event.get("title", ""))
    try:
        tracker.start()
        metrics = _run(event, deps, tracker)
        tracker.done(event["passageId"], metrics)
        return {"status": "done", "jobId": job_id, "passageId": event["passageId"]}
    except Exception:
        LOG.exception("generation failed for job %s", job_id)
        _mark_failed(tracker, job_id)
        return {"status": "failed", "jobId": job_id}


def _mark_failed(tracker: JobTracker, job_id: str) -> None:
    try:
        tracker.failed(FRIENDLY_ERROR)
    except Exception:
        LOG.exception("could not record failure for job %s", job_id)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        clients = create_clients()
    except Exception:
        LOG.exception("generator configuration error")
        return {"status": "failed", "jobId": event.get("jobId", "")}
    return process(event, Dependencies(clients=clients))
