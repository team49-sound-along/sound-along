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

# TTS engine the Generator Lambda runs. kokoro (default) is baked into the image; polly calls Amazon Polly Neural
# (needs the polly:SynthesizeSpeech permission). The synth library reads these from TTS_ENGINE / POLLY_VOICE /
# POLLY_VOICE_ES; the infra only provisions them. Kokoro is the default and needs no environment at all.
TTS_ENGINE_KOKORO = "kokoro"
TTS_ENGINE_POLLY = "polly"
TTS_ENGINES: tuple[str, ...] = (TTS_ENGINE_KOKORO, TTS_ENGINE_POLLY)
DEFAULT_TTS_ENGINE = TTS_ENGINE_KOKORO
DEFAULT_POLLY_VOICE = "Joanna"
DEFAULT_POLLY_VOICE_ES = "Lupe"

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


@dataclass(frozen=True)
class TtsConfig:
    """TTS engine and voices for the Generator Lambda. Voices only matter when engine == polly."""

    engine: str = DEFAULT_TTS_ENGINE
    polly_voice: str = DEFAULT_POLLY_VOICE
    polly_voice_es: str = DEFAULT_POLLY_VOICE_ES

    @property
    def is_polly(self) -> bool:
        return self.engine == TTS_ENGINE_POLLY

    def env(self) -> dict[str, str]:
        """Environment for the generator. Kokoro is the synth default, so it needs no variables."""
        if not self.is_polly:
            return {}
        return {
            "TTS_ENGINE": TTS_ENGINE_POLLY,
            "POLLY_VOICE": self.polly_voice,
            "POLLY_VOICE_ES": self.polly_voice_es,
        }


def parse_tts_engine(value: object) -> str:
    """Validate the `ttsEngine` CDK context value. None means the default (kokoro)."""
    if value is None:
        return DEFAULT_TTS_ENGINE
    if not isinstance(value, str) or value not in TTS_ENGINES:
        raise ValueError(
            f'Invalid CDK context "ttsEngine": {value!r}. Use -c ttsEngine=kokoro (default) or -c ttsEngine=polly.'
        )
    return value


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


def parse_questions_model(value: object) -> str | None:
    """Validate the `questionsModel` CDK context value: `bedrock:<modelId>` or absent. There is deliberately no default model."""
    if value is None:
        return None
    if not isinstance(value, str) or not _MODEL_ID.match(value) or ".." in value:
        raise ValueError(f'Invalid CDK context "questionsModel": {value!r}. Use -c questionsModel=bedrock:<modelId> (there is no default).')
    return value


def parse_questions_enabled(value: object) -> bool:
    """The `questionsEnabled` switch is on only for the exact value true; anything else is off."""
    return value is True or value == "true"
