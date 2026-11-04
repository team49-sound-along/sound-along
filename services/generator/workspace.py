"""Where the chunks of a long document are narrated before they are joined: a private work folder, invisible to the Library.

A chunk runs through the ordinary generator code, unchanged. Two small stand-ins make that safe:
- PrefixedS3 sends every key under `data/` to `raw/work/<document id>/` instead, so a chunk's audio, timing, cards and pictures never appear at a public
  address (CloudFront serves only `/data/*`), and the existing 7-day expiry of `raw/` removes anything a failed run leaves behind;
- NullTable swallows the passage summaries and the index, so a chunk is never listed, and never touches the job the person is watching.
"""
from __future__ import annotations

from typing import Any

WORK_ROOT = "raw/work"


def work_prefix(document_id: str) -> str:
    return f"{WORK_ROOT}/{document_id}/"


class PrefixedS3:
    """An S3 client whose `data/` keys live under the work folder of one document. Everything else is passed through unchanged."""

    def __init__(self, s3: Any, document_id: str) -> None:
        self._s3 = s3
        self._prefix = work_prefix(document_id)

    def _key(self, key: str) -> str:
        return self._prefix + key[len("data/"):] if key.startswith("data/") else key

    def get_object(self, Bucket: str, Key: str, **kwargs: Any) -> Any:  # noqa: N803 (boto3 names)
        return self._s3.get_object(Bucket=Bucket, Key=self._key(Key), **kwargs)

    def put_object(self, Bucket: str, Key: str, **kwargs: Any) -> Any:  # noqa: N803
        return self._s3.put_object(Bucket=Bucket, Key=self._key(Key), **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._s3, name)


class NullTable:
    """A DynamoDB table that holds nothing and remembers nothing: reads are empty, writes are dropped."""

    def query(self, **_kwargs: Any) -> dict[str, Any]:
        return {"Items": []}

    def put_item(self, **_kwargs: Any) -> None:
        return None

    def update_item(self, **_kwargs: Any) -> None:
        return None
