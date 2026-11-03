"""Constants and small value types shared by the stack modules."""
from __future__ import annotations

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


def default_source_paths() -> SourcePaths:
    build = INFRA_ROOT / "build"
    return SourcePaths(
        lambda_dir=build / "api-lambda",
        vm_dir=build / "api-vm",
        generator_dir=REPO_ROOT / "services" / "generator",
        web_dist=REPO_ROOT / "web" / "dist",
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
