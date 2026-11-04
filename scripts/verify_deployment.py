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
    "en": "The class walked to the library on Tuesday. Maya found a book about three red birds. She read for twenty minutes about Tower Bridge in London.",
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
    """The pictures a cards document points at (place pictures, word pictures and the passage figures)."""
    cards = []
    for kind in ("places", "words"):
        group = doc.get(kind) if isinstance(doc, dict) else None
        cards += [c["imageUrl"] for c in (group or {}).values() if isinstance(c, dict) and c.get("imageUrl")]
    figures = doc.get("figures") if isinstance(doc, dict) else None
    cards += [f["imageUrl"] for f in (figures if isinstance(figures, list) else []) if isinstance(f, dict) and f.get("imageUrl")]
    return cards


def draft_paths(passage_id: str) -> list[str]:
    """Where an unreviewed question draft must NOT be reachable through the front door (it lives under raw/, outside /data/*)."""
    return [f"/data/{passage_id}.draft.json", f"/data/{passage_id}.questions.draft.json", f"/raw/questions/{passage_id}.draft.json", f"/data/raw/questions/{passage_id}.draft.json"]


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


def translation_link_problems(catalog: list[dict[str, Any]]) -> list[str]:
    """Every translation link in the catalog must resolve both ways (source lists translation; translation points back)."""
    by_id = {p["id"]: p for p in catalog}
    problems: list[str] = []
    for p in catalog:
        for lang, tid in (p.get("translations") or {}).items():
            target = by_id.get(tid)
            if target is None:
                problems.append(f"{p['id']} links to {lang} translation {tid}, which is not in the catalog")
            elif target.get("translationOf") not in {p["id"], p.get("pairId")} - {None}:  # a human variant shares its AI twin's translation
                problems.append(f"{tid} does not point back to {p['id']}")
        source = p.get("translationOf")
        if source:
            origin = by_id.get(source)
            if origin is None:
                problems.append(f"{p['id']} is a translation of {source}, which is not in the catalog")
            elif not ({p["id"]} & set((origin.get("translations") or {}).values())):
                problems.append(f"{source} does not list {p['id']} as a translation")
    return problems


def series_link_problems(catalog: list[dict[str, Any]]) -> list[str]:
    """The parts of a long document must agree with each other: the same ids and total everywhere, each part at its own place in the list, and
    (once the document is finished) every part present. Parts still being generated are allowed to be missing; a part that disagrees is not."""
    by_id = {p["id"]: p for p in catalog}
    problems: list[str] = []
    for p in catalog:
        s = p.get("series")
        if not s:
            continue
        ids = s.get("partIds") or []
        if s.get("total") != len(ids) or not 1 <= s.get("index", 0) <= len(ids):
            problems.append(f"{p['id']}: series numbers do not add up (part {s.get('index')} of {s.get('total')}, {len(ids)} ids)")
            continue
        if ids[s["index"] - 1] != p["id"]:
            problems.append(f"{p['id']} says it is part {s['index']} but the list has {ids[s['index'] - 1]} there")
        for i, pid in enumerate(ids, start=1):
            other = by_id.get(pid)
            if other is not None and (other.get("series") or {}).get("partIds") != ids:
                problems.append(f"part {i} ({pid}) disagrees with part {s['index']} about which parts belong together")
    return problems


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

    def translation_links() -> str:
        problems = translation_link_problems(state["catalog"])
        assert not problems, "; ".join(problems[:3])
        linked = sum(1 for p in state["catalog"] if p.get("translationOf"))
        return f"{linked} translated passage(s), every link resolves both ways"

    def series_links() -> str:
        problems = series_link_problems(state["catalog"])
        assert not problems, "; ".join(problems[:3])
        documents = {(p.get("series") or {}).get("id") for p in state["catalog"] if p.get("series")} - {None}
        return f"{len(documents)} multi-part document(s), every part agrees with the others"

    def drafts_unreachable() -> str:
        """A question draft a student could fetch is exactly the failure the review step guards against."""
        for url in draft_paths(state["passage"]):
            r = request("GET", f"{site}{url}")
            assert r.status != 200 or b'"questions"' not in r.body, f"{url} is reachable (HTTP {r.status}): a draft must never be served"
        return f"{len(draft_paths(state['passage']))} draft locations are not served"

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
                     ("audio range request (seeking)", audio_range), ("word and place cards", cards), ("translation links", translation_links), ("multi-part documents", series_links), ("question drafts are not served", drafts_unreachable), ("write through the front door", signed_write),
                     ("security headers", security_headers), ("insights", insights), ("listening test clips", listening)):
        if "passage" not in state and name in ("timing document", "audio range request (seeking)", "word and place cards", "question drafts are not served"):
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

            def live_cards() -> str:
                """A passage nobody prepared gets place cards and pictures at publish time. Wikipedia being unreachable is a warning."""
                r = request("GET", f"{site}/data/{state['generated']}.cards.json")
                if r.status == 404:
                    report.emit("WARN", "live place cards", "no cards for the new passage (Wikipedia unreachable from the generator, or no place found)")
                    return "skipped (warning above)"
                assert r.status == 200, f"HTTP {r.status}"
                doc = r.json()
                problem = cards_problem({"words": {"_": {}}, "places": doc.get("places", {})})
                assert problem is None, problem
                assert doc.get("places"), "cards document has no places"
                pictures = image_urls(doc)
                for url in pictures:
                    img = request("GET", f"{site}{url}")
                    assert img.status == 200 and img.headers.get("content-type", "").startswith("image/"), f"{url}: HTTP {img.status}"
                return f"{len(doc['places'])} place(s), {len(pictures)} picture(s) load as images, reviewed={doc.get('reviewed')}"

            report.check("live place cards for the new passage", live_cards)

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
