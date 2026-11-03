"""Fake S3, DynamoDB table and TTS engine for handler tests."""
from __future__ import annotations

import io
import json
from typing import Any

import numpy as np

from engine import SAMPLE_RATE, SentenceAudio
from word_mapper import EngineToken


class FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.content_types: dict[str, str] = {}
        self.content_encodings: dict[str, str] = {}
        self.cache_controls: dict[str, str] = {}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str, ContentEncoding: str | None = None, CacheControl: str | None = None) -> None:
        self.objects[Key] = Body
        self.content_types[Key] = ContentType
        if CacheControl:
            self.cache_controls[Key] = CacheControl
        if ContentEncoding:
            self.content_encodings[Key] = ContentEncoding


class FakeTable:
    """Records update_item calls and applies simple 'SET #a = :a' expressions; rejects floats like boto3."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def _reject_floats(value: Any) -> None:
        if isinstance(value, float):
            raise TypeError("Float types are not supported. Use Decimal types instead.")
        if isinstance(value, dict):
            for v in value.values():
                FakeTable._reject_floats(v)
        if isinstance(value, list):
            for v in value:
                FakeTable._reject_floats(v)

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues) -> None:
        self._reject_floats(ExpressionAttributeValues)
        item = self.items.setdefault((Key["pk"], Key["sk"]), {"pk": Key["pk"], "sk": Key["sk"]})
        assignments = UpdateExpression.removeprefix("SET ").split(", ")
        for assignment in assignments:
            name_ref, value_ref = (part.strip() for part in assignment.split("="))
            item[ExpressionAttributeNames[name_ref]] = ExpressionAttributeValues[value_ref]
        self.history.append(dict(item))

    def put_item(self, Item: dict[str, Any]) -> None:
        self._reject_floats(Item)
        self.items[(Item["pk"], Item["sk"])] = Item

    def query(self, KeyConditionExpression: str, ExpressionAttributeValues: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        pk = ExpressionAttributeValues[":pk"]
        return {"Items": [dict(item) for (p, _), item in self.items.items() if p == pk]}

    def job(self, job_id: str) -> dict[str, Any]:
        return self.items[("JOB", job_id)]

    def steps(self, job_id: str) -> list[str]:
        return [h["step"] for h in self.history if h["sk"] == job_id and "step" in h]


class FakeEngine:
    name = "fake"
    voice = "fake_voice"

    def __init__(self, *_args, **_kwargs) -> None:  # the handler passes the job input; the fake ignores it
        pass

    def synthesize(self, sentence: str) -> SentenceAudio:
        words = sentence.split()
        tokens = tuple(EngineToken(w, i * 0.2, i * 0.2 + 0.15) for i, w in enumerate(words))
        audio = (0.1 * np.sin(np.linspace(0, 200, int(SAMPLE_RATE * 0.2 * max(len(words), 1))))).astype(np.float32)
        return SentenceAudio(audio, tokens)


def fake_encoder(audio: np.ndarray, sample_rate: int, kbps: int = 48) -> bytes:
    return b"MP3:" + str(len(audio)).encode()


def raw_passage(title: str = "The Park", content: str = "<p>We went to the park. It was fun.</p>") -> bytes:
    return json.dumps({"uuid": "x", "title": title, "content": content, "source": "generated"}).encode()


JOB_ID = "11111111-1111-1111-1111-111111111111"
PASSAGE_ID = "22222222-2222-2222-2222-222222222222"
EVENT = {"jobId": JOB_ID, "passageId": PASSAGE_ID, "title": "The Park", "rawKey": f"raw/{PASSAGE_ID}.json"}
