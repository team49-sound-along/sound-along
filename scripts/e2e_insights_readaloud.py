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
import re
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
    page.wait_for_selector("[data-testid=ra-headline], [data-testid=ra-empty]")
    return page


def open_details(page, testid):
    """Opens a collapsed section (Show the numbers / Settings and privacy) if it is closed."""
    box = page.locator(f"[data-testid={testid}]")
    if box.get_attribute("open") is None:
        box.locator("summary").first.click()
    return box


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
        check("settings and privacy start collapsed, at the bottom", page.locator("[data-testid=ra-settings]").get_attribute("open") is None and page.get_by_role("switch").count() == 0)
        open_details(page, "ra-settings")
        page.wait_for_selector("[data-testid=ra-disclosure]")
        check("the school disclosure is next to the switches", "Check your school" in page.locator("[data-testid=ra-disclosure]").inner_text() and "Google in Chrome and Edge, Apple in Safari" in page.locator("[data-testid=ra-disclosure]").inner_text())
        check("the reader-code note is plain", "Codes are not names" in page.locator("[data-testid=ra-readers-note]").inner_text())
        axe_clean(page, "insights, empty")
        page.close()

        # 2. Three sessions with a skipped word; the payload is counts and positions only
        counts = [read_with_skip(student, BASE, PID, WORDS, K, sent) for _ in range(2)]
        page = teacher_insights(teacher, BASE)
        thin = page.locator("[data-testid=ra-thin]")
        check("with fewer than 3 readers a friendly explanation says what to do", thin.count() == 1 and "Once 3 students have read this passage aloud you will see which words are hard." in thin.inner_text() and "Read aloud with the mic" in thin.inner_text(), thin.inner_text() if thin.count() else "no ra-thin")
        check("no word or heat-map is shown yet", page.locator("[data-testid=ra-heat]").count() == 0 and page.locator("[data-testid=ra-top-words]").count() == 0)
        axe_clean(page, "insights, not enough readers yet")
        page.close()
        counts += [read_with_skip(student, BASE, PID, WORDS, K, sent)]
        check("each session sends exactly one result", counts == [1, 1, 1], str(counts))
        body = json.loads(sent[0])
        check("the result has counts and word positions only", set(body) <= {"passageId", "classId", "language", "wordsTotal", "wordsRead", "finished", "retried", "words"} and {"i": K, "kind": "skipped"} in body["words"] and body["classId"] == CLASS_ID, sent[0])
        check("no transcript, name or device id is sent", not any(x in sent[0] for x in ("transcript", "heard", "name", "device", "readerCode")))
        check("the word text is not sent", SKIPPED not in sent[0].lower())

        # 3. Teacher: organisation view, then class and passage filters
        page = teacher_insights(teacher, BASE)
        section = page.locator("[data-testid=ra-section]")
        check("the section is called Reading aloud", section.locator("h3").inner_text() == "Reading aloud")
        page.wait_for_selector("[data-testid=ra-heat]")  # the page opens on the passage with the most reads
        headline = page.locator("[data-testid=ra-headline]").inner_text()
        check("a plain headline names the passage, finishing and hard words", TITLE in headline and "finished" in headline and "1 word tripped up many readers." in headline, headline)
        check("no jargon in the headline", not any(w in headline.lower() for w in ("session", "retry", "distinct")))
        status = page.locator("[data-testid=ra-status]")
        check("for all classes the finishing graph is one plain bar per class with the class name on it", CLASS_NAME in status.inner_text() and "stopped part-way" in status.inner_text() and status.locator("svg rect.bar, svg rect.track").count() >= 2, status.inner_text())
        check("the passage text itself is the heat-map", len(page.locator("[data-testid=ra-heat]").inner_text()) > 100 and "Darker = more students stumbled here" in section.inner_text())
        shaded = page.get_by_role("button", name=re.compile(r"Missed by 3 of 3 readers"))
        check("the skipped word is shaded and keyboard focusable", shaded.count() >= 1 and shaded.first.evaluate("e => e.tabIndex") >= 0 and SKIPPED in shaded.first.inner_text().lower())
        shaded.first.click()
        check("tapping a word shows how many readers missed it", "Missed by 3 of 3 readers" in page.locator("[data-testid=ra-heat-detail]").inner_text())
        shaded.first.focus()
        check("focusing a word shows the same", SKIPPED in page.locator("[data-testid=ra-heat-detail]").inner_text().lower())
        top = page.locator("[data-testid=ra-top-words]")
        check("a bar chart ranks the hardest words, with the count written beside each bar", "Which 5 words were missed most?" in top.inner_text() and SKIPPED in top.inner_text().lower() and "3 of 3 readers" in top.inner_text(), top.inner_text())
        titles = page.locator("[data-testid=ra-section] h4").all_inner_texts()
        check("three graphs, each titled with a plain question", titles[:3] == ["Did they finish?", "Which words are hard?", "Which 5 words were missed most?"] and page.locator("[data-testid=ra-section] section[aria-labelledby^=q] svg").count() >= 2, str(titles))
        check("at most three graphs on the main view", page.locator("[data-testid=ra-section] section[aria-labelledby=q1] svg, [data-testid=ra-section] section[aria-labelledby=q3] svg").count() + (1 if page.locator("[data-testid=ra-heat]").count() else 0) <= 3)
        check("no table or number grid on the main view", page.locator("[data-testid=ra-section] table:visible, [data-testid=ra-section] summary:visible:has-text('Show as a table')").count() == 0)
        check("the top word has more than colour: bold and underlined", shaded.first.evaluate("e => getComputedStyle(e).textDecorationLine === 'underline' && Number(getComputedStyle(e).fontWeight) >= 700"))
        steps = page.locator("[data-testid=ra-steps]").inner_text()
        check("what to do next names the word", "Practice this word together" in steps and SKIPPED in steps.lower(), steps)
        check("the privacy note is short and friendly", "groups of 3 or more readers" in page.locator("[data-testid=ra-min-note]").inner_text())
        numbers = page.locator("[data-testid=ra-numbers]")
        check("the numbers are collapsed until asked for", numbers.get_attribute("open") is None and not numbers.locator("dl").is_visible())
        open_details(page, "ra-numbers")
        check("the improving line waits for two weeks of reads and says so", "once students have read in two different weeks" in numbers.inner_text())
        check("Show the numbers opens the raw numbers and text tables", numbers.locator("dl").is_visible() and "Reads" in numbers.inner_text() and numbers.locator("details summary", has_text="Show as a table").count() >= 3 and numbers.locator("svg [tabindex='0']").count() >= 1)
        axe_clean(page, "insights, organisation view with the numbers open")
        numbers.locator("summary").first.click()
        check("Show the numbers closes again", numbers.get_attribute("open") is None)
        page.select_option("#ra-class", CLASS_ID)
        page.wait_for_selector(f"[data-testid=ra-headline]:has-text('{CLASS_NAME}')")
        page.wait_for_selector("[data-testid=ra-heat]")
        ring = page.locator("[data-testid=ra-status] svg[role=img]")
        check("the class view shows the word and one big percentage ring", SKIPPED in section.inner_text().lower() and ring.count() == 1 and "finished" in ring.get_attribute("aria-label"))
        check("the class name leads the headline", CLASS_NAME in page.locator("[data-testid=ra-headline]").inner_text())
        axe_clean(page, "insights, class view")
        page.set_viewport_size({"width": 375, "height": 800})
        check("phone width has no sideways scroll", no_sideways_scroll(page), str(wide_elements(page)))
        open_details(page, "ra-numbers")
        open_details(page, "ra-settings")
        check("phone width with everything open has no sideways scroll", no_sideways_scroll(page), str(wide_elements(page)))
        page.set_viewport_size({"width": 1100, "height": 900})
        page.close()

        # 4. Sharing off: nothing is sent
        page = teacher_insights(teacher, BASE)
        open_details(page, "ra-settings")
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
        page.wait_for_selector("[data-testid=ra-reader-bars] svg")
        bars = [t.text_content() for t in page.locator("[data-testid=ra-reader-bars] svg text.lbl").all()]
        vals = [t.text_content() for t in page.locator("[data-testid=ra-reader-bars] svg text.val").all()]
        check("three readers are plain bars in letter order", len(bars) == 3 and bars == sorted(bars), str(bars))
        words = ("New", "Improving", "Steady", "Support")
        check("each bar has a percentage and one word", all(any(v.endswith(w) for w in words) for v in vals) and sum(v.endswith("New") for v in vals) == 2, str(vals))
        check("no dots, lines or tables in the reader list", page.locator("[data-testid=ra-readers] polyline, [data-testid=ra-readers] table:visible, [data-testid=ra-readers] summary:visible").count() == 0)
        text = page.locator("[data-testid=ra-readers]").inner_text()
        check("no name, grade or ranking appears", not any(w in text.lower() for w in ("grade:", "rank", "best", "worst", "score")))
        check("no select to pick one child out", page.locator("#rr-code").count() == 0)
        axe_clean(page, "insights, reader cards")
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
