#!/usr/bin/env python3
"""Bundle the CMS API with esbuild into infra/build/ (run before `cdk synth` / `cdk deploy`).

  build/api-lambda/src/index.mjs  + config/*.json   handler: src/index.handler  (cmsHost=lambda)
  build/api-vm/src/serverVm.js    + config/*.json   `node src/serverVm.js`       (cmsHost=ec2)

The app finds config/*.json (voices.json, polly-voices.json, polly-voice-ratings.json) at ../config relative to the bundle, hence the src/ + config/ layout.
Needs Node and npx (esbuild is fetched by npx at the pinned version).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ESBUILD_VERSION = "0.25.10"
NODE_TARGET = "node18"
INFRA_ROOT = Path(__file__).resolve().parent
API_ROOT = INFRA_ROOT.parent / "services" / "api"
BUILD_ROOT = INFRA_ROOT / "build"

# ESM output keeps import.meta.url (used to locate voices.json). CommonJS dependencies such as express call
# require(), so ESM needs a require shim.
REQUIRE_SHIM = "import { createRequire as __cr } from 'node:module'; const require = __cr(import.meta.url);"


def esbuild_command(entry: Path, outfile: Path) -> list[str]:
    # The AWS SDK is bundled (not left to the runtime) so Lambda and the VM run identical, pinned SDK code.
    command = [
        "npx", "--yes", f"esbuild@{ESBUILD_VERSION}",
        str(entry),
        f"--outfile={outfile}",
        "--bundle", "--platform=node", f"--target={NODE_TARGET}", "--format=esm", "--minify", "--sourcemap",
        f"--banner:js={REQUIRE_SHIM}",
        "--log-level=warning",
    ]
    return command


def bundle(entry_relative: str, out_name: str, entry_out: str) -> Path:
    out_dir = BUILD_ROOT / out_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "src").mkdir(parents=True)
    (out_dir / "config").mkdir()
    subprocess.run(
        esbuild_command(API_ROOT / entry_relative, out_dir / "src" / entry_out),
        check=True,
        cwd=API_ROOT,
    )
    for config_file in sorted((API_ROOT / "config").glob("*.json")):  # every config document the API reads at start (voices, Polly voices, Polly ratings)
        shutil.copy(config_file, out_dir / "config" / config_file.name)
    (out_dir / "package.json").write_text(json.dumps({"type": "module"}) + "\n")
    return out_dir


def main() -> int:
    if not (API_ROOT / "node_modules").is_dir():
        sys.stderr.write(f"Run `npm ci` in {API_ROOT} first (the bundle needs express and the AWS SDK).\n")
        return 1
    for out_dir in (
        bundle("src/aws/lambda.js", "api-lambda", "index.mjs"),
        bundle("src/aws/serverVm.js", "api-vm", "serverVm.js"),
    ):
        sys.stdout.write(f"bundled {out_dir}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
