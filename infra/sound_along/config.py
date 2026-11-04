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
    polly_engine: str | None = None  # neural (the generator's default) | generative | long-form | standard

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
            **({"POLLY_ENGINE": self.polly_engine} if self.polly_engine else {}),
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


def parse_reader_insights(value: object) -> bool:
    """`readerInsights` (-c readerInsights=true) turns on anonymous per-reader progress codes in the read-aloud insights. Off unless the exact value
    true: reader codes must not be collected on a deployed site before teacher sign-in exists."""
    return value is True or value == "true"


# A DNS hostname for the public site (-c siteDomain=sound-along.online). Labels are 1-63 chars of letters, digits
# and hyphens (not leading/trailing), and there are at least two labels. None means CloudFront's *.cloudfront.net
# domain only (no custom domain, no ACM certificate).
_DOMAIN_NAME = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")


def parse_site_domain(value: object) -> str | None:
    """Validate the `siteDomain` CDK context value: a DNS hostname such as sound-along.online, or absent.

    When set, the stack adds the domain as a CloudFront alternate domain name with an ACM certificate (in us-east-1)
    and creates Route 53 alias records in the matching public hosted zone. Absent means the default *.cloudfront.net
    domain only.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not _DOMAIN_NAME.match(value):
        raise ValueError(
            f'Invalid CDK context "siteDomain": {value!r}. Use a hostname, for example -c siteDomain=sound-along.online.'
        )
    return value.lower()


_POLLY_VOICE = re.compile(r"^[A-Za-zÁ-ú]{3,20}$")
POLLY_ENGINES = ("neural", "generative", "long-form", "standard")


def parse_polly_voice(value: object, key: str) -> str | None:
    """An optional Polly voice name (-c pollyVoice=Joanna, -c pollyVoiceEs=Lupe): letters only. None keeps the default."""
    if value is None:
        return None
    if not isinstance(value, str) or not _POLLY_VOICE.match(value):
        raise ValueError(f'Invalid CDK context "{key}": {value!r}. Letters only, for example Joanna or Lupe.')
    return value


def parse_polly_engine(value: object) -> str | None:
    """An optional Polly engine (-c pollyEngine=neural|generative|long-form|standard). None keeps the generator's default (neural)."""
    if value is None:
        return None
    if not isinstance(value, str) or value.lower() not in POLLY_ENGINES:
        raise ValueError(f'Invalid CDK context "pollyEngine": {value!r}. Use one of {", ".join(POLLY_ENGINES)}.')
    return value.lower()


# CDK context keys the CI/CD pipeline passes on to its own `cdk deploy` (ttsEngine, cmsHost and alertEmail are passed separately). A key read in
# app.py but missing here would silently fall back to its default whenever the pipeline deploys.
PIPELINE_CONTEXT_KEYS = ("pollyVoice", "pollyVoiceEs", "pollyEngine", "translateModel", "siteDomain", "questionsModel", "questionsEnabled", "readerInsights")
