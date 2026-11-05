"""AWS Lambda entry point: draft questions for one published passage.

Event: {"passageId": "<ai passage id>"}. Reads data/<id>.timing.json, writes ONLY raw/questions/<id>.draft.json (never under data/, which CloudFront serves).
Environment: BUCKET, QUESTIONS_MODEL (for example bedrock:<modelId>), QUESTIONS_ENABLED ("true" to run; anything else is the kill switch),
QUESTIONS_COUNT (default 4), QUESTIONS_REGION (default us-west-2).
Tested here with a fake S3 and a fake model; see docs/QUESTIONS.md for the sandbox steps that test it against Bedrock.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from qg_adapters import DEFAULT_REGION, AdapterError, ModelAdapter, adapter_from_spec
from qg_cost import price_for
from qg_pipeline import GenerationError, generate_draft

LOG = logging.getLogger(__name__)
_SAFE_ID = re.compile(r"^[0-9A-Za-z_-]+$")
DRAFT_PREFIX = "raw/questions/"


def _missing(error: Exception) -> bool:
    code = getattr(error, "response", {}).get("Error", {}).get("Code")
    return code in ("NoSuchKey", "404", "NotFound")


def _read_json(s3: Any, bucket: str, key: str) -> Any:
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body)  # timing files are stored gzipped


def _already_reviewed(s3: Any, bucket: str, passage_id: str) -> bool:
    try:
        return _read_json(s3, bucket, f"data/{passage_id}.questions.json").get("reviewed") is True
    except Exception as error:  # noqa: BLE001 (no file yet is the normal case; anything else is also treated as "not reviewed")
        if not _missing(error):
            LOG.warning("could not read reviewed questions for %s: %s", passage_id, error)
        return False


def _min_interval(env: Mapping[str, str]) -> float | None:
    """Seconds between Bedrock calls (QUESTIONS_MIN_INTERVAL). Unset means the adapter default; a bad value is a configuration error, so it is loud."""
    raw = env.get("QUESTIONS_MIN_INTERVAL")
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if not 0 <= value <= 30:
        raise ValueError(f"QUESTIONS_MIN_INTERVAL must be a number of seconds from 0 to 30, not {raw!r}")
    return value


def handle(
    event: Mapping[str, Any],
    *,
    s3: Any,
    bucket: str,
    env: Mapping[str, str],
    adapter_factory: Callable[[str, str], ModelAdapter] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    passage_id = str(event.get("passageId", ""))
    if not _SAFE_ID.match(passage_id):
        raise ValueError(f"missing or unsafe passageId: {passage_id!r}")
    if env.get("QUESTIONS_ENABLED") != "true":
        return {"status": "disabled", "passageId": passage_id}
    spec = env.get("QUESTIONS_MODEL", "")
    if not spec:
        raise ValueError("QUESTIONS_MODEL is not set (for example bedrock:<modelId>)")
    if _already_reviewed(s3, bucket, passage_id):
        return {"status": "skipped", "passageId": passage_id, "reason": "reviewed questions already exist"}

    interval = _min_interval(env)
    factory = adapter_factory or (lambda spec, region: adapter_from_spec(spec, region, min_interval=interval))
    try:
        timing = _read_json(s3, bucket, f"data/{passage_id}.timing.json")
        adapter = factory(spec, env.get("QUESTIONS_REGION", DEFAULT_REGION))
        draft = generate_draft(
            timing, adapter, n=int(env.get("QUESTIONS_COUNT", "4")), model=spec, price=price_for(spec), today=today or date.today().isoformat()
        )
    except (GenerationError, AdapterError, ValueError, KeyError, OSError) as error:
        LOG.exception("question draft failed for %s", passage_id)
        return {"status": "failed", "passageId": passage_id, "error": str(error)}
    except Exception as error:  # noqa: BLE001 (a missing S3 key is a boto ClientError, which this module does not import)
        if _missing(error):
            return {"status": "failed", "passageId": passage_id, "error": f"timing file not found for {passage_id}"}
        raise

    s3.put_object(Bucket=bucket, Key=f"{DRAFT_PREFIX}{passage_id}.draft.json", Body=json.dumps(draft, ensure_ascii=False).encode(), ContentType="application/json")
    return {"status": "drafted", "passageId": passage_id, "kept": len(draft["questions"]), "dropped": len(draft["dropped"]), "metrics": draft["metrics"]}


def handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Production entry point. boto3 is imported here (it is part of the Lambda runtime), so tests never need it."""
    import boto3

    return handle(event, s3=boto3.client("s3"), bucket=os.environ["BUCKET"], env=os.environ)
