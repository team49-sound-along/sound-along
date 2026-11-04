"""End-to-end check of the anonymous read-aloud insights, with a FAKE speech recognizer (no microphone, no network, no AWS).

It starts the real API + built web app (run `cd web && npm run build` first) on a SCRATCH copy of the demo data, then:
  students read with skipped words (3 sessions), the teacher opens Insights and sees the word and the suggested next step (org and class views);
  the sharing switch off means nothing is sent; the mic switch off hides the button; a failing settings endpoint fails safe;
  with "progress by reader" on, three different devices read and the teacher sees a reader's own progress charts and summary;
  charts have text alternatives and focusable points; phone width has no sideways scroll; optional axe on every view.

Usage:  python3 scripts/e2e_insights_readaloud.py /path/to/data      (a folder with *.timing.json and *.mp3, e.g. the project's data/)
        AXE_JS=/path/to/axe.min.js python3 scripts/e2e_insights_readaloud.py /path/to/data
The data folder is copied to a temporary folder first; your copy is never changed. Exit code 0 only when every step passes.
"""
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
AXE = os.environ.get("AXE_JS", "")
AXE_SOURCE = pathlib.Path(AXE).read_text() if AXE else ""
CLASS_ID, CLASS_NAME = "cls-g3-p2", "Period 2 Reading"
FAKE = """
window.__recs = [];
window.SpeechRecognition = class { constructor() { window.__recs.push(this); }
  start() { setTimeout(() => this.onstart && this.onstart(), 0); }
  stop() { setTimeout(() => this.onend && this.onend(), 0); } };
window.__say = (items) => { const r = window.__recs[window.__recs.length - 1];
  r.onresult({ resultIndex: 0, results: items.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f })) }); };
"""
STUDENT = "localStorage.setItem('soundalong.role','student');"
failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def axe_clean(page, name):
    if not AXE:
        print("SKIP  axe: " + name + " (set AXE_JS)")
        return
    page.evaluate(AXE_SOURCE)  # evaluated, not injected as a tag: the site's content security policy blocks inline scripts
    result = page.evaluate("axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }).then(r => r.violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).join(' | ')))")
    check("axe clean: " + name, result == [], str(result))


def get(url):
    with urllib.request.urlopen(url) as res:
        return json.load(res)["data"]


def send(base, method, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req) as res:
        return json.load(res)["data"]


def start_server(data_dir):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "DATA_DIR": str(data_dir), "READER_INSIGHTS": "true", "GENERATION_ENABLED": "false"}
    proc = subprocess.Popen(["node", str(ROOT / "services" / "api" / "server.js")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            get(base + "/api/health")
            return proc, base
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    proc.kill()
    raise SystemExit("the API did not start")


def pick_passage(base):
    for p in get(base + "/api/passages"):
        if p.get("language", "en") != "en":
            continue
        timing = json.load(urllib.request.urlopen(f"{base}/data/{p['id']}.timing.json"))
        words = timing["words"]
        for k in range(4, len(words) - 8):
            if len(words[k]["text"].strip(".,;:!?\"'")) >= 5 and words[k]["text"].strip(".,;:!?\"'").isalpha():
                return p["id"], p["title"], [w["text"] for w in words], k
    raise SystemExit("no English passage with enough words in the data folder")


def read_with_skip(ctx, base, pid, words, k, record):
    """One student session: skips word k, then closes the panel (which sends the result when sharing is on)."""
    page = ctx.new_page()
    page.add_init_script(FAKE)
    page.add_init_script("localStorage.setItem('soundalong.readAloudMode.v1','stop');")
    page.on("request", lambda r: record.append(r.post_data) if r.method == "POST" and "/api/read-aloud/results" in r.url else None)
    page.goto(f"{base}/#/read/{pid}")
    page.wait_for_selector("#w-0")
    button = page.get_by_role("button", name="Read aloud with the mic")
    button.wait_for(timeout=5000)
    button.click()
    page.get_by_role("button", name="Start reading").click()
    wait_until(lambda: page.evaluate("window.__recs.length") == 1)
    heard = " ".join(w for i, w in enumerate(words) if i != k).lower()
    page.evaluate("t => window.__say([[t, true]])", heard)
    page.wait_for_selector(".callout")
    before = len(record)
    page.get_by_role("button", name="Close").first.click()
    page.wait_for_timeout(500)
    sent = len(record) - before
    page.close()
    return sent


def teacher_insights(ctx, base, query=""):
    page = ctx.new_page()
    page.goto(f"{base}/#/insights{query}")
    page.wait_for_selector("[data-testid=ra-section] h3")
    page.wait_for_selector("[data-testid=ra-scope], [data-testid=ra-empty]")
    return page


def no_sideways_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def wide_elements(page):
    """For the failure message: the elements that stick out past the window's right edge."""
    return page.evaluate("document.documentElement.scrollWidth + ' > ' + window.innerWidth + ': ' + [...document.querySelectorAll('body *')].filter(e => !e.closest('.table-wrap') && e.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 6).map(e => e.tagName + '.' + (e.className.baseVal ?? e.className)).join(' ')")


def wait_until(predicate, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


tmp = pathlib.Path(tempfile.mkdtemp(prefix="sa-e2e-ra-"))
data = tmp / "data"
shutil.copytree(SRC, data, ignore=shutil.ignore_patterns("state.json", "*.questions.json"))
proc, BASE = start_server(data)
try:
    PID, TITLE, WORDS, K = pick_passage(BASE)
    SKIPPED = WORDS[K].strip(".,;:!?\"'").lower()
    send(BASE, "POST", "/api/assignments", {"passageId": PID, "classId": CLASS_ID, "soundAlong": True})  # students open the passage as this class
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        student = browser.new_context(viewport={"width": 1100, "height": 900})
        student.add_init_script(STUDENT)
        teacher = browser.new_context(viewport={"width": 1100, "height": 900})
        sent = []

        # 1. Before any session
        page = teacher_insights(teacher, BASE)
        check("empty state before any reading", page.locator("[data-testid=ra-empty]").count() == 1)
        check("the school disclosure is next to the switches", "Check your school" in page.locator("[data-testid=ra-disclosure]").inner_text() and "Google in Chrome and Edge, Apple in Safari" in page.locator("[data-testid=ra-disclosure]").inner_text())
        check("the reader-code note is plain", "Codes are not names" in page.locator("[data-testid=ra-readers-note]").inner_text())
        axe_clean(page, "insights, empty")
        page.close()

        # 2. Three sessions with a skipped word; the payload is counts and positions only
        counts = [read_with_skip(student, BASE, PID, WORDS, K, sent) for _ in range(3)]
        check("each session sends exactly one result", counts == [1, 1, 1], str(counts))
        body = json.loads(sent[0])
        check("the result has counts and word positions only", set(body) <= {"passageId", "classId", "language", "wordsTotal", "wordsRead", "finished", "retried", "words"} and {"i": K, "kind": "skipped"} in body["words"] and body["classId"] == CLASS_ID, sent[0])
        check("no transcript, name or device id is sent", not any(x in sent[0] for x in ("transcript", "heard", "name", "device", "readerCode")))
        check("the word text is not sent", SKIPPED not in sent[0].lower())

        # 3. Teacher: organisation view, then class and passage filters
        page = teacher_insights(teacher, BASE)
        section = page.locator("[data-testid=ra-section]")
        check("the section is called Reading aloud", section.locator("h3").inner_text() == "Reading aloud")
        check("the skipped word is listed with its count", f"{SKIPPED}" in section.inner_text().lower() and "3 of 3 sessions" in section.inner_text())
        check("the suggested next step names the word", f'Add "{SKIPPED}" to this class\'s word practice.'.lower() in section.inner_text().lower())
        check("the minimum-group notice is shown", "at least 3 sessions" in page.locator("[data-testid=ra-min-note]").inner_text())
        check("charts have a text alternative and focusable points", section.locator("details summary", has_text="Show as a table").count() >= 3 and section.locator("svg [tabindex='0']").count() >= 1)
        axe_clean(page, "insights, organisation view")
        page.select_option("#ra-passage", PID)
        page.wait_for_selector("[data-testid=ra-scope]:has-text('" + TITLE.replace("'", "\\'") + "')")
        page.select_option("#ra-class", CLASS_ID)
        page.wait_for_selector(f"[data-testid=ra-scope]:has-text('{CLASS_NAME}')")
        check("the class view still shows the word", SKIPPED in section.inner_text().lower() and "Finish rate by class" not in section.inner_text())
        axe_clean(page, "insights, class view")
        page.set_viewport_size({"width": 375, "height": 800})
        check("phone width has no sideways scroll", no_sideways_scroll(page), str(wide_elements(page)))
        page.set_viewport_size({"width": 1100, "height": 900})
        page.close()

        # 4. Sharing off: nothing is sent
        page = teacher_insights(teacher, BASE)
        page.get_by_role("switch", name=f"{CLASS_NAME}: Share anonymous word counts with the teacher").click()
        share_switch = page.get_by_role("switch", name=f"{CLASS_NAME}: Share anonymous word counts with the teacher")
        check("the sharing switch turned off", wait_until(lambda: share_switch.get_attribute("aria-checked") == "false"))
        page.close()
        before = len(sent)
        n = read_with_skip(student, BASE, PID, WORDS, K, sent)
        check("with sharing off nothing is sent", n == 0 and len(sent) == before, str(n))
        probe = student.new_page()
        probe.goto(f"{BASE}/#/read/{PID}")
        probe.get_by_role("button", name="Read aloud with the mic").wait_for()
        probe.get_by_role("button", name="Read aloud with the mic").click()
        check("the panel says nothing is shared", "Nothing about your reading is shared" in probe.locator("[data-testid=ra-privacy]").inner_text())
        check("the panel shows the speech-service line and no consent screen", "speech service listens" in probe.locator("section.ra").inner_text() and probe.get_by_role("button", name="I agree, continue").count() == 0)
        probe.close()
        send(BASE, "PUT", "/api/read-aloud/settings", {"classId": CLASS_ID, "share": True})

        # 5. Microphone off hides the button; a failing settings endpoint fails safe
        send(BASE, "PUT", "/api/read-aloud/settings", {"classId": CLASS_ID, "mic": False})
        page = student.new_page()
        page.add_init_script(FAKE)
        page.goto(f"{BASE}/#/read/{PID}")
        page.wait_for_selector("#w-0")
        page.wait_for_timeout(800)
        check("with the microphone off the button is hidden", page.get_by_role("button", name="Read aloud with the mic").count() == 0)
        page.close()
        send(BASE, "PUT", "/api/read-aloud/settings", {"classId": CLASS_ID, "mic": True})
        failing = []
        page = student.new_page()
        page.add_init_script(FAKE)
        page.route("**/api/read-aloud/settings", lambda r: r.fulfill(status=500, json={"success": False, "error": "x"}))
        page.on("request", lambda r: failing.append(r.url) if r.method == "POST" and "/api/read-aloud/results" in r.url else None)
        page.goto(f"{BASE}/#/read/{PID}")
        page.wait_for_selector("#w-0")
        page.wait_for_timeout(1000)
        check("a failing settings endpoint hides the button and sends nothing", page.get_by_role("button", name="Read aloud with the mic").count() == 0 and failing == [])
        page.close()

        # 6. Progress by reader: three devices (fresh storage each), the teacher sees one reader's own progress
        send(BASE, "PUT", "/api/read-aloud/settings", {"classId": CLASS_ID, "readers": True})
        codes = []
        for n in range(3):
            device = browser.new_context(viewport={"width": 1100, "height": 900})
            device.add_init_script(STUDENT)
            for _ in range(2 if n == 0 else 1):
                read_with_skip(device, BASE, PID, WORDS, K, sent)
            device.close()
        check("a reader code is sent only when the class switch is on", sum('"readerCode"' in b for b in sent) == 4 and all('"readerCode"' not in b for b in sent[:3]), str(sum('"readerCode"' in b for b in sent)))
        page = teacher_insights(teacher, BASE)
        page.select_option("#ra-class", CLASS_ID)
        page.wait_for_selector("[data-testid=ra-readers]")
        page.wait_for_selector("#rr-code")
        options = page.locator("#rr-code option").all_inner_texts()
        check("three readers are listed by code, alphabetically", len(options) == 4 and options[1:] == sorted(options[1:]), str(options))
        busiest = [o for o in options[1:] if "2 sessions" in o]
        page.select_option("#rr-code", label=busiest[0])
        page.wait_for_selector("[data-testid=ra-reader-summary]")
        text = page.locator("[data-testid=ra-readers]").inner_text()
        check("the reader view has a plain summary and both charts", "Reader" in page.locator("[data-testid=ra-reader-summary]").inner_text() and "Share of the passage read, by session" in text and "Skipped and different words, by session" in text)
        check("no name, grade or ranking appears", not any(w in text.lower() for w in ("grade:", "rank", "best", "worst", "score")))
        axe_clean(page, "insights, reader view")
        page.set_viewport_size({"width": 375, "height": 800})
        check("reader view at phone width has no sideways scroll", no_sideways_scroll(page), str(wide_elements(page)))
        page.close()

        # 7. Switching readers off stops showing them
        send(BASE, "PUT", "/api/read-aloud/settings", {"classId": CLASS_ID, "readers": False})
        page = teacher_insights(teacher, BASE)
        page.select_option("#ra-class", CLASS_ID)
        page.wait_for_timeout(600)
        check("with readers off the reader view is gone", page.locator("[data-testid=ra-readers]").count() == 0)
        page.close()
        browser.close()
finally:
    proc.terminate()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nFAILED: " + ", ".join(failures) if failures else "\nAll steps passed.")
sys.exit(1 if failures else 0)
