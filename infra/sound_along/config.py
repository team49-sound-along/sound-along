"""Constants and small value types shared by the stack modules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REGION = "us-west-2"
PROJECT_TAG = "sound-along"
BUDGET_LIMIT_USD = 500
BUDGET_THRESHOLD_PERCENTS: tuple[int, ...] = (25, 50, 80)

CMS_HOST_EC2 = "ec2"
CMS_HOST_LAMBDA = "lambda"
CMS_HOSTS: tuple[str, ...] = (CMS_HOST_EC2, CMS_HOST_LAMBDA)
DEFAULT_CMS_HOST = CMS_HOST_EC2

# The CMS API listens here on the VM; CloudFront reaches it over plain HTTP (the security group only admits CloudFront).
API_PORT = 8080

# Environment shared by both CMS hosts (Lambda environment, VM systemd unit).
API_ENV_DEFAULTS: dict[str, str] = {
    "GENERATION_ENABLED": "true",
    "GENERATE_PER_MINUTE": "3",
    "MAX_CONCURRENT_JOBS": "2",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SourcePaths:
    """Where the stack finds its inputs. `lambda_dir` / `vm_dir` are produced by `python bundle_api.py`."""

    lambda_dir: Path
    vm_dir: Path
    generator_dir: Path
    web_dist: Path
    questions_dir: Path


def default_source_paths() -> SourcePaths:
    build = INFRA_ROOT / "build"
    return SourcePaths(
        lambda_dir=build / "api-lambda",
        vm_dir=build / "api-vm",
        generator_dir=REPO_ROOT / "services" / "generator",
        web_dist=REPO_ROOT / "web" / "dist",
        questions_dir=REPO_ROOT / "services" / "questions",
    )


def parse_cms_host(value: object) -> str:
    """Validate the `cmsHost` CDK context value. None means the default (ec2)."""
    if value is None:
        return DEFAULT_CMS_HOST
    if not isinstance(value, str) or value not in CMS_HOSTS:
        raise ValueError(
            f'Invalid CDK context "cmsHost": {value!r}. Use -c cmsHost=ec2 (default) or -c cmsHost=lambda.'
        )
    return value


def require_bundle(path: Path, what: str) -> Path:
    """Fail with an actionable message when the esbuild output folder has not been created."""
    if not path.is_dir():
        raise FileNotFoundError(
            f"{what} not found at {path}. Run `python bundle_api.py` in infra/ first (needs Node and npx)."
        )
    return path


_MODEL_ID = re.compile(r"^bedrock:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_AMAZON_TRANSLATE = re.compile(r"^amazon(:(informal|formal))?$")


def parse_questions_model(value: object) -> str | None:
    """Validate the `questionsModel` CDK context value: `bedrock:<modelId>` or absent. There is deliberately no default model."""
    if value is None:
        return None
    if not isinstance(value, str) or not _MODEL_ID.match(value) or ".." in value:
        raise ValueError(f'Invalid CDK context "questionsModel": {value!r}. Use -c questionsModel=bedrock:<modelId> (there is no default).')
    return value


def parse_translate_model(value: object) -> str | None:
    """Validate the `translateModel` CDK context value: `bedrock:<modelId>`, `amazon`, `amazon:informal`, `amazon:formal`, or absent. Absent means the built-in Opus-MT translator only; there is no default model."""
    if value is None:
        return None
    if isinstance(value, str) and _AMAZON_TRANSLATE.match(value):
        return value  # Amazon Translate: amazon, amazon:informal or amazon:formal
    if not isinstance(value, str) or not _MODEL_ID.match(value) or ".." in value:
        raise ValueError(f'Invalid CDK context "translateModel": {value!r}. Use -c translateModel=bedrock:<modelId>, amazon or amazon:informal (there is no default).')
    return value


def parse_questions_enabled(value: object) -> bool:
    """The `questionsEnabled` switch is on only for the exact value true; anything else is off."""
    return value is True or value == "true"


TTS_ENGINES = ("kokoro", "polly")
_POLLY_VOICE = re.compile(r"^[A-Za-zÁ-ú]{3,20}$")
POLLY_ENGINES = ("neural", "generative", "long-form", "standard")


def parse_tts_engine(value: object) -> str:
    """The `ttsEngine` CDK context value: kokoro (default, runs inside the image) or polly (Amazon Polly, billed per character)."""
    if value is None:
        return "kokoro"
    if not isinstance(value, str) or value.lower() not in TTS_ENGINES:
        raise ValueError(f'Invalid CDK context "ttsEngine": {value!r}. Use -c ttsEngine=kokoro or -c ttsEngine=polly.')
    return value.lower()


def parse_polly_options(voice_en: object, voice_es: object, engine: object) -> dict[str, str]:
    """Optional Polly choices, validated: -c pollyVoice=Joanna -c pollyVoiceEs=Lupe -c pollyEngine=neural. Empty when none are given."""
    out: dict[str, str] = {}
    for key, value in (("POLLY_VOICE", voice_en), ("POLLY_VOICE_ES", voice_es)):
        if value is not None:
            if not isinstance(value, str) or not _POLLY_VOICE.match(value):
                raise ValueError(f"Invalid Polly voice {value!r} for {key}: letters only, for example Joanna or Lupe.")
            out[key] = value
    if engine is not None:
        if not isinstance(engine, str) or engine.lower() not in POLLY_ENGINES:
            raise ValueError(f'Invalid CDK context "pollyEngine": {engine!r}. Use one of {", ".join(POLLY_ENGINES)}.')
        out["POLLY_ENGINE"] = engine.lower()
    return out
