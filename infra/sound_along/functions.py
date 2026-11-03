from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .config import API_ENV_DEFAULTS
from .iam_util import api_s3_policies, object_access


def _log_group(scope: Construct, construct_id: str) -> logs.LogGroup:
    return logs.LogGroup(
        scope,
        construct_id,
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )


@dataclass(frozen=True)
class ApiFunctionProps:
    code_dir: Path
    bucket: s3.IBucket
    table: dynamodb.ITable


def create_api_function(scope: Construct, props: ApiFunctionProps) -> lambda_.Function:
    """The CMS API as a Lambda (cmsHost=lambda). Code is the esbuild output from `python bundle_api.py`."""
    fn = lambda_.Function(
        scope,
        "ApiFunction",
        code=lambda_.Code.from_asset(str(props.code_dir)),
        handler="src/index.handler",
        # The customer's stack requires Node 18.x. AWS deprecated nodejs18.x on Sep 1 2025, but creating functions
        # through CloudFormation/CDK stays allowed until Jul 29 2027, so it is acceptable for this event.
        # Revisit (move to nodejs22.x) before that date.
        runtime=lambda_.Runtime.NODEJS_18_X,
        architecture=lambda_.Architecture.ARM_64,
        memory_size=512,
        timeout=Duration.seconds(30),
        reserved_concurrent_executions=5,
        log_group=_log_group(scope, "ApiLogs"),
        environment={
            "BUCKET": props.bucket.bucket_name,
            "TABLE_NAME": props.table.table_name,
            **API_ENV_DEFAULTS,
        },
    )
    props.table.grant_read_write_data(fn)
    for statement in api_s3_policies(props.bucket):
        fn.add_to_role_policy(statement)
    return fn


@dataclass(frozen=True)
class GeneratorFunctionProps:
    generator_dir: Path
    bucket: s3.IBucket
    table: dynamodb.ITable


def create_generator_function(scope: Construct, props: GeneratorFunctionProps) -> lambda_.DockerImageFunction:
    fn = lambda_.DockerImageFunction(
        scope,
        "GeneratorFunction",
        code=lambda_.DockerImageCode.from_image_asset(
            str(props.generator_dir), platform=ecr_assets.Platform.LINUX_ARM64
        ),
        architecture=lambda_.Architecture.ARM_64,
        memory_size=4096,
        timeout=Duration.seconds(600),
        reserved_concurrent_executions=2,
        log_group=_log_group(scope, "GeneratorLogs"),
        environment={"BUCKET": props.bucket.bucket_name, "TABLE_NAME": props.table.table_name},
    )
    props.table.grant_read_write_data(fn)
    fn.add_to_role_policy(object_access(props.bucket, ["s3:GetObject"], "raw/*"))
    fn.add_to_role_policy(object_access(props.bucket, ["s3:PutObject"], "data/*"))
    return fn
