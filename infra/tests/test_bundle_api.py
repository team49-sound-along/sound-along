"""The API bundle must carry every config document the API reads at startup: a missing one makes the service crash-loop on the VM (the site answers 504)."""
import re
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
API = INFRA.parent / "services" / "api"
sys.path.insert(0, str(INFRA))


def test_the_bundle_copies_every_json_file_of_the_api_config_folder(tmp_path, monkeypatch):
    import bundle_api

    monkeypatch.setattr(bundle_api.subprocess, "run", lambda *a, **k: None)  # no esbuild needed here
    monkeypatch.setattr(bundle_api, "BUILD_ROOT", tmp_path)
    out = bundle_api.bundle("src/serverVm.js", "api-vm", "serverVm.js")
    names = {p.name for p in (out / "config").glob("*.json")}
    expected = {p.name for p in (API / "config").glob("*.json")}
    assert expected <= names, f"missing from the bundle: {sorted(expected - names)}"


def test_every_config_file_the_api_source_names_exists_in_the_config_folder():
    named = set()
    for source in (API / "src").rglob("*.js"):
        named |= set(re.findall(r'"([A-Za-z0-9_-]+\.json)"', source.read_text()))
    in_config = {p.name for p in (API / "config").glob("*.json")}
    config_named = {n for n in named if n.startswith(("voices", "polly-voice"))}
    assert config_named <= in_config, f"named in the code but not in services/api/config: {sorted(config_named - in_config)}"
