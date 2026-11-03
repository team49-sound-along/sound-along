"""Generator Lambda: raw passage JSON in S3 -> MP3 + timing JSON in S3, job and passage items in DynamoDB."""
from __future__ import annotations

import _bootstrap  # noqa: F401  (must come before synth imports)

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from artifacts import Artifacts, generate_artifacts
from audio import encode_mp3
from clients import Clients, create_clients
from dynamo import JobTracker, now_iso, put_passage_summary
from engine import SAMPLE_RATE
from engine_cache import get_engine
from summary import passage_summary

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

FRIENDLY_ERROR = "We could not generate audio for this text. Try shorter text or remove unusual symbols."
Encoder = Callable[[np.ndarray, int], bytes]


@dataclass(frozen=True)
class Dependencies:
    clients: Clients
    engine_factory: Callable[[], Any]
    encoder: Encoder = encode_mp3


def _read_raw(clients: Clients, raw_key: str) -> dict[str, Any]:
    body = clients.s3.get_object(Bucket=clients.bucket, Key=raw_key)["Body"].read()
    return json.loads(body)


def _put(clients: Clients, key: str, body: bytes, content_type: str) -> None:
    clients.s3.put_object(Bucket=clients.bucket, Key=key, Body=body, ContentType=content_type)


def _publish(deps: Dependencies, passage_id: str, artifacts: Artifacts, workdir: Path) -> dict[str, Any]:
    mp3_path = workdir / f"{passage_id}.mp3"
    mp3_path.write_bytes(deps.encoder(artifacts.audio, SAMPLE_RATE))
    timing_path = workdir / f"{passage_id}.timing.json"
    timing_path.write_text(json.dumps(artifacts.timing, ensure_ascii=False), encoding="utf-8")
    _put(deps.clients, f"data/{passage_id}.mp3", mp3_path.read_bytes(), "audio/mpeg")
    _put(deps.clients, f"data/{passage_id}.timing.json", timing_path.read_bytes(), "application/json")
    summary = passage_summary(artifacts.timing, now_iso())
    put_passage_summary(deps.clients.table, summary)
    return summary


def _run(event: dict[str, Any], deps: Dependencies, tracker: JobTracker) -> dict[str, Any]:
    passage_id = event["passageId"]
    raw = _read_raw(deps.clients, event["rawKey"])
    passage = {**raw, "uuid": passage_id, "title": raw.get("title") or event.get("title")}
    artifacts = generate_artifacts(passage, deps.engine_factory(), tracker.step)
    tracker.step("publish")
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        _publish(deps, passage_id, artifacts, Path(tmp))
    return artifacts.metrics


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
    return process(event, Dependencies(clients=clients, engine_factory=get_engine))
