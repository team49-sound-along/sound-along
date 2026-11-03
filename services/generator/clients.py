"""boto3 client factory. The handler receives a Clients bundle so tests can pass fakes."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Clients:
    s3: Any  # boto3 S3 client (get_object, put_object)
    table: Any  # boto3 DynamoDB Table resource (put_item, update_item)
    bucket: str


def create_clients(env: Mapping[str, str] = os.environ) -> Clients:
    bucket, table_name = env.get("BUCKET"), env.get("TABLE_NAME")
    if not bucket or not table_name:
        raise ConfigError("BUCKET and TABLE_NAME environment variables are required")
    import boto3  # imported lazily so tests without boto3 can use fakes

    return Clients(s3=boto3.client("s3"), table=boto3.resource("dynamodb").Table(table_name), bucket=bucket)
