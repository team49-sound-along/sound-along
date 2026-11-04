"""A long document is generated as a series of parts. Each part's job input says which series it belongs to; this keeps only a well-formed description."""
from __future__ import annotations

import re
from typing import Any, Optional

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
MAX_PARTS = 40


def clean_series(raw: Any) -> Optional[dict[str, Any]]:
    """{id, index, total, title, partIds} when `raw` is a valid series description, otherwise None (the passage is then an ordinary single passage)."""
    if not isinstance(raw, dict):
        return None
    ids, index, total, series_id = raw.get("partIds"), raw.get("index"), raw.get("total"), raw.get("id")
    if not (isinstance(ids, list) and 2 <= len(ids) <= MAX_PARTS and all(isinstance(i, str) and _UUID.match(i) for i in ids)):
        return None
    if not (isinstance(series_id, str) and _UUID.match(series_id)):
        return None
    if not (isinstance(total, int) and total == len(ids) and isinstance(index, int) and 1 <= index <= total):
        return None
    title = raw.get("title")
    return {"id": series_id, "index": index, "total": total, "title": title[:120] if isinstance(title, str) else "", "partIds": list(ids)}
