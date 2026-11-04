from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import Aws, Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .config import API_ENV_DEFAULTS
from .config import REGION
from .config import TtsConfig
from .iam_util import api_s3_policies, list_bucket, object_access, polly_synthesize


US_PROFILE_REGIONS = ("us-east-1", "us-east-2", "us-west-2")  # where a "us." cross-region inference profile may route a request


def bedrock_invoke_statements(model_value: str) -> list[iam.PolicyStatement]:
    """InvokeModel permission for exactly one model, least privilege.

    A plain model id (amazon.nova-lite-v1:0) needs only that foundation model in this region. A cross-region profile id ("us.amazon.nova-lite-v1:0") needs the
    inference profile itself, and the foundation model in each region it may route to, but only when the call comes through THAT profile."""
    model_id = model_value.removeprefix("bedrock:")
    if model_id.startswith("us."):
        profile_arn = f"arn:aws:bedrock:{REGION}:{Aws.ACCOUNT_ID}:inference-profile/{model_id}"
        base = model_id.removeprefix("us.")
        return [
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[profile_arn]),
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{region}::foundation-model/{base}" for region in US_PROFILE_REGIONS],
                conditions={"StringLike": {"bedrock:InferenceProfileArn": profile_arn}},
            ),
        ]
    return [iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[f"arn:aws:bedrock:{REGION}::foundation-model/{model_id}"])]


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
    reader_insights: bool = False


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
            "READER_INSIGHTS": "true" if props.reader_insights else "false",
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
    translate_model: str | None = None  # "bedrock:<modelId>": a context-aware LLM translator in front of Opus-MT; None = no Bedrock permission at all
    bedrock_min_interval: float = 1.1  # seconds between this function's Bedrock requests (the account allows about one per second in total)
    tts: TtsConfig = TtsConfig()  # "polly": narration with Amazon Polly (adds polly:SynthesizeSpeech); kokoro runs inside the image and needs no permission


def create_generator_function(scope: Construct, props: GeneratorFunctionProps) -> lambda_.DockerImageFunction:
    # The real generator Dockerfile COPYs services/parse and services/synth (siblings of services/generator), so its
    # build context must be the directory that holds `services/` (the repo root), not services/generator itself.
    # When generator_dir lives under a `services/` folder (the real layout) use that parent as the context and point
    # `file` at services/generator/Dockerfile; otherwise (the self-contained test fixtures) use generator_dir as the
    # context with its own Dockerfile. `exclude` keeps the staged context (and the asset hash) small; the repo-root
    # .dockerignore mirrors it for raw `docker build` runs.
    if props.generator_dir.parent.name == "services":
        context_root = props.generator_dir.parents[1]
        dockerfile_rel = (props.generator_dir / "Dockerfile").relative_to(context_root).as_posix()
    else:
        context_root = props.generator_dir
        dockerfile_rel = "Dockerfile"
    fn = lambda_.DockerImageFunction(
        scope,
        "GeneratorFunction",
        code=lambda_.DockerImageCode.from_image_asset(
            str(context_root),
            file=dockerfile_rel,
            platform=ecr_assets.Platform.LINUX_ARM64,
            exclude=[
                "**/__pycache__",
                "**/*.pyc",
                "**/.pytest_cache",
                ".git",
                ".venv",
                "**/.venv",
                "**/node_modules",
                "web",
                "infra",
                "data",
                "eval",
                "samples",
                "docs",
                "ReadWorks",
                "requirements",
                "*.log",
                "services/api",
                "services/align",
                "services/publish",
                "services/eval",
                "services/questions",
                "services/generator/tests",
                "**/test_*.py",
            ],
        ),
        architecture=lambda_.Architecture.ARM_64,
        memory_size=4096,
        timeout=Duration.seconds(900),  # the Lambda maximum: translating and narrating the longest text can take minutes on 2 CPUs
        reserved_concurrent_executions=1 if (props.translate_model or "").startswith("bedrock:") else 2,  # one caller at a time keeps Bedrock under the rate limit
        log_group=_log_group(scope, "GeneratorLogs"),
        environment={"BUCKET": props.bucket.bucket_name, "TABLE_NAME": props.table.table_name,
                     **({"TRANSLATE_MODEL": props.translate_model, "TRANSLATE_REGION": REGION, "TRANSLATE_MIN_INTERVAL": str(props.bedrock_min_interval)} if props.translate_model else {}),
                     **props.tts.env()},
    )
    props.table.grant_read_write_data(fn)
    fn.add_to_role_policy(object_access(props.bucket, ["s3:GetObject"], "raw/*"))
    # It also READS what it published: the previous timing (skip unchanged input), reviewed cards (never replace them), and in translate mode the
    # source timing, cards and pictures it must link and translate. ListBucket makes a missing key a clean 404 instead of a 403 the code would swallow.
    fn.add_to_role_policy(object_access(props.bucket, ["s3:GetObject"], "data/*"))
    fn.add_to_role_policy(list_bucket(props.bucket, ["data/*", "raw/work/*"]))
    fn.add_to_role_policy(object_access(props.bucket, ["s3:PutObject"], "data/*"))
    # The chunks of a long document are narrated in a private work folder (raw/work/<document id>/, never served, and `raw/` expires after 7 days anyway),
    # then joined into one passage and the folder is deleted.
    fn.add_to_role_policy(object_access(props.bucket, ["s3:PutObject", "s3:DeleteObject"], "raw/work/*"))
    if props.tts.is_polly:
        fn.add_to_role_policy(polly_synthesize())
    if props.translate_model and props.translate_model.startswith("amazon"):  # Amazon Translate has no resource-level permissions for plain text
        fn.add_to_role_policy(iam.PolicyStatement(actions=["translate:TranslateText"], resources=["*"]))
    elif props.translate_model:  # one model only, and only when the operator chose it
        for statement in bedrock_invoke_statements(props.translate_model):
            fn.add_to_role_policy(statement)
    return fn


@dataclass(frozen=True)
class QuestionsFunctionProps:
    code_dir: Path
    bucket: s3.IBucket
    model: str | None = None  # "bedrock:<modelId>"; None means no model, no Bedrock permission, and the function stays off
    enabled: bool = False
    bedrock_min_interval: float = 1.1  # seconds between this function's Bedrock requests (the account allows about one per second in total)


def create_questions_function(scope: Construct, props: QuestionsFunctionProps) -> lambda_.Function:
    """Drafts practice questions for a published passage. Best effort and bounded: reserved concurrency 2, a kill switch that defaults to off,
    S3 read of data/* and write of raw/questions/* only (never data/*, so a draft can never be served), and Bedrock permission for one model only."""
    on = bool(props.model) and props.enabled
    environment = {"BUCKET": props.bucket.bucket_name, "QUESTIONS_ENABLED": "true" if on else "false", "QUESTIONS_REGION": REGION, "QUESTIONS_COUNT": "4"}
    if props.model:
        environment["QUESTIONS_MODEL"] = props.model
        environment["QUESTIONS_MIN_INTERVAL"] = str(props.bedrock_min_interval)
    fn = lambda_.Function(
        scope,
        "QuestionsFunction",
        runtime=lambda_.Runtime.PYTHON_3_14,
        architecture=lambda_.Architecture.ARM_64,
        handler="qg_handler.handler",
        code=lambda_.Code.from_asset(str(props.code_dir), exclude=["test_*.py", "conftest.py", "__pycache__", "*.pyc", ".pytest_cache"]),
        memory_size=256,
        timeout=Duration.seconds(120),
        reserved_concurrent_executions=1 if props.model else 2,  # one caller at a time keeps Bedrock under the rate limit
        log_group=_log_group(scope, "QuestionsLogs"),
        environment=environment,
    )
    fn.add_to_role_policy(object_access(props.bucket, ["s3:GetObject"], "data/*"))
    fn.add_to_role_policy(list_bucket(props.bucket, ["data/*"]))
    fn.add_to_role_policy(object_access(props.bucket, ["s3:PutObject"], "raw/questions/*"))
    if props.model:
        for statement in bedrock_invoke_statements(props.model):
            fn.add_to_role_policy(statement)
    return fn
