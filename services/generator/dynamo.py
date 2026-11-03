"""DynamoDB helpers: Decimal conversion and JOB / PASSAGE item writes."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

JOB_TTL_SECONDS = 7 * 24 * 3600


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_dynamo(value: Any) -> Any:
    """Recursively convert floats to Decimal (boto3's resource layer rejects float)."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str, Decimal)):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(k): to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    raise TypeError(f"Cannot store {type(value).__name__} in DynamoDB")


@dataclass
class JobTracker:
    """Updates one JOB item. Repeated identical steps are collapsed so the step sequence is clean."""

    table: Any
    job_id: str
    title: str
    _last_step: str | None = field(default=None, init=False)

    def _update(self, sets: dict[str, Any]) -> None:
        names = {f"#{k}": k for k in sets}
        values = {f":{k}": to_dynamo(v) for k, v in sets.items()}
        expression = "SET " + ", ".join(f"#{k} = :{k}" for k in sets)
        self.table.update_item(
            Key={"pk": "JOB", "sk": self.job_id},
            UpdateExpression=expression,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def start(self) -> None:
        self._last_step = "parse"
        self._update(
            {
                "id": self.job_id,
                "title": self.title,
                "status": "running",
                "step": "parse",
                "ttl": int(time.time()) + JOB_TTL_SECONDS,
            }
        )

    def step(self, step: str) -> None:
        if step == self._last_step:
            return
        self._last_step = step
        self._update({"status": "running", "step": step})

    def done(self, passage_id: str, metrics: dict[str, Any]) -> None:
        self._update(
            {"status": "done", "step": "done", "passageId": passage_id, "metrics": metrics, "error": None, "finishedAt": now_iso()}
        )

    def failed(self, message: str) -> None:
        self._update({"status": "failed", "error": message, "finishedAt": now_iso()})


def list_passage_items(table: Any) -> list[dict[str, Any]]:
    """Every PASSAGE summary item. String key conditions keep this free of boto3 imports (the Table resource accepts them)."""
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"KeyConditionExpression": "pk = :pk", "ExpressionAttributeValues": {":pk": "PASSAGE"}}
    while True:
        page = table.query(**kwargs)
        items.extend(page.get("Items", []))
        if not page.get("LastEvaluatedKey"):
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def put_passage_summary(table: Any, summary: dict[str, Any]) -> None:
    table.put_item(Item=to_dynamo({"pk": "PASSAGE", "sk": summary["id"], **summary}))
