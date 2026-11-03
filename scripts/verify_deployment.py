"""Check a running Sound Along site end to end. Standard library only, so it runs anywhere.

  python scripts/verify_deployment.py --site https://dxxxx.cloudfront.net [--generate] [--language es]
  python scripts/verify_deployment.py --site http://127.0.0.1:3101 --generate          # the same checks, locally

Every check prints PASS, FAIL or SKIP with the evidence. Exit code 1 if any check FAILS. With --generate it submits a real
generation job and reports the measured seconds and the cost fields from the job's own metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

SHORT_TEXT = {
    "en": "The class walked to the library on Tuesday. Maya found a book about three red birds. She read for twenty minutes.",
    "es": "Los niños van al parque todos los días. Allí juegan con sus amigos y comen frutas. Después regresan a casa felices.",
}


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def request(method: str, url: str, body: Optional[bytes] = None, headers: Optional[dict[str, str]] = None, timeout: int = 60) -> Response:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (URL comes from the operator)
            return Response(res.status, {k.lower(): v for k, v in res.headers.items()}, res.read())
    except urllib.error.HTTPError as err:
        return Response(err.code, {k.lower(): v for k, v in err.headers.items()}, err.read())


def monotonic_starts(words: list[dict[str, Any]]) -> bool:
    starts = [w["start_ms"] for w in words]
    return all(a <= b for a, b in zip(starts, starts[1:]))


def parse_content_range(value: str) -> Optional[tuple[int, int, int]]:
    """'bytes 0-1023/52000' -> (0, 1023, 52000)"""
    try:
        unit, rest = value.split(" ", 1)
        span, total = rest.split("/")
        first, last = span.split("-")
        return (int(first), int(last), int(total)) if unit == "bytes" else None
    except (ValueError, AttributeError):
        return None


def needs_cards(passage: dict[str, Any]) -> bool:
    """English sample texts voiced by the read-aloud engine carry a reviewed cards document (docs/CARDS.md).
    Human variants open their AI passage's cards; Spanish, teacher uploads and this script's own job have none."""
    return passage.get("source") == "sample" and passage.get("language") == "en" and passage.get("engine") not in (None, "human")


def image_urls(doc: Any) -> list[str]:
    """The place pictures a cards document points at (word cards never carry one)."""
    places = doc.get("places") if isinstance(doc, dict) else None
    return [c["imageUrl"] for c in (places or {}).values() if isinstance(c, dict) and c.get("imageUrl")]


def cards_problem(doc: Any) -> Optional[str]:
    """None when the cards document has the shape the reader expects, otherwise what is wrong."""
    if not isinstance(doc, dict) or not isinstance(doc.get("words"), dict) or not isinstance(doc.get("places"), dict):
        return "expected an object with `words` and `places` objects"
    if not doc["words"]:
        return "no word cards"
    offsite = [u for u in image_urls(doc) if not (isinstance(u, str) and u.startswith("/data/") and "://" not in u)]
    if offsite:
        return f"imageUrl must be a /data/ path on our own origin, found {offsite[0]!r}"
    return None


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def emit(self, status: str, name: str, detail: str = "") -> None:
        if status == "FAIL":
            self.failed += 1
        sys.stdout.write(f"{status:<5} {name}{(': ' + detail) if detail else ''}\n")
        sys.stdout.flush()

    def check(self, name: str, fn: Callable[[], str]) -> None:
        try:
            self.emit("PASS", name, fn())
        except AssertionError as err:
            self.emit("FAIL", name, str(err))
        except Exception as err:  # noqa: BLE001 (a check must never crash the whole run)
            self.emit("FAIL", name, f"{type(err).__name__}: {err}")


def run(site: str, generate: bool, language: str, timeout_s: int) -> int:
    site = site.rstrip("/")
    report = Report()
    state: dict[str, Any] = {}

    def page() -> str:
        r = request("GET", f"{site}/")
        assert r.status == 200 and b"Sound Along" in r.body, f"HTTP {r.status}"
        return f"HTTP 200, {len(r.body)} bytes"

    def health() -> str:
        data = request("GET", f"{site}/api/health").json()
        assert data["success"] and data["data"]["status"] == "ok", data
        return f"generation enabled = {data['data']['generation']['enabled']}"

    def passages() -> str:
        data = request("GET", f"{site}/api/passages").json()["data"]
        assert data, "no passages (run the seed script)"
        state["passage"] = data[0]["id"]
        state["catalog"] = data
        return f"{len(data)} passages; using {data[0]['title']!r}"

    def timing() -> str:
        r = request("GET", f"{site}/data/{state['passage']}.timing.json", headers={"Accept-Encoding": "gzip"})
        assert r.status == 200, f"HTTP {r.status}"
        encoding = r.headers.get("content-encoding", "none")
        doc = r.json() if encoding == "none" else json.loads(__import__("gzip").decompress(r.body))
        assert doc["words"] and monotonic_starts(doc["words"]), "timing empty or not monotonic"
        return f"{len(doc['words'])} words, monotonic, content-encoding {encoding}"

    def audio_range() -> str:
        r = request("GET", f"{site}/data/{state['passage']}.mp3", headers={"Range": "bytes=0-1023"})
        assert r.status == 206, f"expected 206 Partial Content, got {r.status} (seeking would break)"
        span = parse_content_range(r.headers.get("content-range", ""))
        assert span and span[1] == 1023, f"bad Content-Range {r.headers.get('content-range')!r}"
        return f"206, {r.headers.get('content-range')}, {r.headers.get('content-type')}"

    def cards() -> str:
        wanted = [p for p in state["catalog"] if needs_cards(p)]
        assert wanted, "no English sample text in the catalog to check (run the seed script)"
        for passage in wanted:
            r = request("GET", f"{site}/data/{passage['id']}.cards.json")
            assert r.status == 200, f"{passage['title']!r} has no cards document (HTTP {r.status}); seed uploads data/<id>.cards.json"
            problem = cards_problem(r.json())
            assert problem is None, f"{passage['title']!r}: {problem}"
        pictures = 0
        for passage in wanted:
            for url in image_urls(request("GET", f"{site}/data/{passage['id']}.cards.json").json()):
                r = request("GET", f"{site}{url}")
                assert r.status == 200 and r.headers.get("content-type", "").startswith("image/"), f"{url}: HTTP {r.status} {r.headers.get('content-type')}"
                pictures += 1
        return f"{len(wanted)} English sample text(s) each have a valid cards document; {pictures} place picture(s) load as images"

    def signed_write() -> str:
        current = request("GET", f"{site}/api/settings").json()["data"]
        body = json.dumps({k: current[k] for k in ("voice", "voiceEs", "speed", "mp3Kbps") if k in current}).encode()
        signed = request("PUT", f"{site}/api/settings", body, {"content-type": "application/json", "x-amz-content-sha256": sha256_hex(body)})
        assert signed.status == 200, f"write WITH x-amz-content-sha256 failed: HTTP {signed.status}"
        unsigned = request("PUT", f"{site}/api/settings", body, {"content-type": "application/json"})
        return f"with hash header HTTP 200; without it HTTP {unsigned.status} (403 is expected behind CloudFront OAC, 200 on the VM)"

    def security_headers() -> str:
        r = request("GET", f"{site}/api/health")
        assert r.headers.get("x-content-type-options") == "nosniff", "X-Content-Type-Options missing"
        return "nosniff present" + ("; HTTPS" if site.startswith("https://") else "; plain HTTP (local run)")

    def insights() -> str:
        data = request("GET", f"{site}/api/insights").json()["data"]
        return f"{data['catalog']['passages']} passages, projected catalog cost fields present: {'projectedCatalog' in data['cost']}"

    def listening() -> str:
        trial = request("GET", f"{site}/api/ratings/trial").json()["data"]
        return "a trial is available" if trial else "no clips yet (run scripts/build_samples.py, then seed)"

    for name, fn in (("site loads", page), ("API health", health), ("passage list", passages), ("timing document", timing),
                     ("audio range request (seeking)", audio_range), ("word and place cards", cards), ("write through the front door", signed_write),
                     ("security headers", security_headers), ("insights", insights), ("listening test clips", listening)):
        if "passage" not in state and name in ("timing document", "audio range request (seeking)", "word and place cards"):
            report.emit("SKIP", name, "no passage to test")
            continue
        report.check(name, fn)

    if generate:
        def job() -> str:
            body = json.dumps({"title": "Deployment check", "text": SHORT_TEXT[language], "language": language}).encode()
            r = request("POST", f"{site}/api/generate", body, {"content-type": "application/json", "x-amz-content-sha256": sha256_hex(body)})
            assert r.status == 202, f"HTTP {r.status}: {r.body[:200]!r}"
            job_id, started, steps = r.json()["data"]["jobId"], time.time(), []
            while time.time() - started < timeout_s:
                data = request("GET", f"{site}/api/jobs/{job_id}").json()["data"]
                if not steps or steps[-1] != data["step"]:
                    steps.append(data["step"])
                if data["status"] == "failed":
                    raise AssertionError(f"job failed: {data['error']}")
                if data["status"] == "done":
                    m = data["metrics"]
                    state["generated"] = data["passageId"]
                    return (f"done in {time.time() - started:.0f}s via steps {' > '.join(steps)}; audio {m.get('audioSeconds')}s, "
                            f"generate {m.get('generateSeconds')}s, estimated Lambda ${m.get('estimatedLambdaUsd')} "
                            "(replace the estimate with Billed Duration from the CloudWatch REPORT line)")
                time.sleep(2)
            raise AssertionError(f"job did not finish within {timeout_s}s")

        report.check(f"generate a {language.upper()} passage end to end", job)
        if "generated" in state:
            def result() -> str:
                doc = request("GET", f"{site}/data/{state['generated']}.timing.json", headers={"Accept-Encoding": "gzip"})
                body = doc.body if doc.headers.get("content-encoding") != "gzip" else __import__("gzip").decompress(doc.body)
                words = json.loads(body)["words"]
                unaligned = sum(1 for w in words if not w.get("aligned", True))
                assert words and monotonic_starts(words)
                return f"{len(words)} words, {unaligned} not exactly aligned"

            report.check("generated passage is readable", result)

    sys.stdout.write(f"\n{'ALL CHECKS PASSED' if not report.failed else str(report.failed) + ' CHECK(S) FAILED'}\n")
    return 1 if report.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", required=True, help="site origin, e.g. https://dxxxx.cloudfront.net or http://127.0.0.1:3101")
    parser.add_argument("--generate", action="store_true", help="also run a real generation job (costs a few cents on AWS)")
    parser.add_argument("--language", choices=("en", "es"), default="en")
    parser.add_argument("--timeout", type=int, default=240, help="seconds to wait for the generation job")
    args = parser.parse_args()
    return run(args.site, args.generate, args.language, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
