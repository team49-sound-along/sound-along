"""Browser check for the pronunciation help in "Read aloud with the microphone", with a FAKE speech recognizer and a FAKE audio player
(no real microphone, no sound, no network).

It serves web/dist (run `cd web && npm run build` first), skips a word, opens "Help me say it", and checks: syllables (English and
Spanish), "Hear it slowly" slowing the audio element, the "Say it with me" success and retry paths, "Add to My words" showing up in
Practice, the end-of-reading "Words to practice" with add-all, and no slow button for a word whose timing is only estimated.
Optional accessibility check: set AXE_JS to the path of axe-core's axe.min.js.

Usage: python3 scripts/e2e_pronunciation.py        (exit code 0 only when every step passes)
"""
import functools, http.server, json, os, pathlib, re, sys, threading
from playwright.sync_api import sync_playwright

DIST = pathlib.Path(__file__).resolve().parent.parent / "web" / "dist"
AXE = os.environ.get("AXE_JS", "")


def passage(text, lang, aligned=True):
    words, t = [], 0
    for i, w in enumerate(text.split()):
        words.append({"i": i, "text": w, "start_ms": t, "end_ms": t + 350, "aligned": aligned, "sentence": 0, "paragraph": 0})
        t += 400
    return {"id": "p-" + lang, "title": "Test passage", "language": lang, "engine": "polly", "duration_ms": t, "words": words}


PASSAGES = {
    "p-en": passage("I like it because it is fun today.", "en"),
    "p-es": passage("El niño está muy cansado hoy.", "es"),
    "p-est": passage("I like it because it is fun today.", "en", aligned=False),
}
FAKE = """
window.__recs = [];
window.SpeechRecognition = class { constructor() { this.stopped = false; window.__recs.push(this); }
  start() { this.started = true; setTimeout(() => this.onstart && this.onstart(), 0); }
  stop() { this.stopped = true; setTimeout(() => this.onend && this.onend(), 0); } };
window.__say = (items) => { const r = window.__recs[window.__recs.length - 1];
  r.onresult({ resultIndex: 0, results: items.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f })) }); };
// Fake audio: nothing plays, but every speed the player sets is written down.
window.__rates = [];
const d = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'playbackRate');
Object.defineProperty(HTMLMediaElement.prototype, 'playbackRate', { configurable: true, get() { return d.get.call(this); }, set(v) { window.__rates.push(v); d.set.call(this, v); } });
HTMLMediaElement.prototype.play = function () { return Promise.resolve(); };
HTMLMediaElement.prototype.pause = function () {};
"""

failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def axe_clean(page, name):
    if not AXE:
        print("SKIP  axe: " + name + " (set AXE_JS)")
        return
    if not page.evaluate("typeof axe !== 'undefined'"):
        page.add_script_tag(path=AXE)
    result = page.evaluate("axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }).then(r => r.violations.map(v => v.id + ': ' + v.nodes.length))")
    check("axe clean: " + name, result == [], str(result))


def open_reader(ctx, pid):
    page = ctx.new_page()
    page.add_init_script(FAKE)
    page.route(re.compile(r".*/data/.*\.(mp3|json)$"), lambda r: r.fulfill(status=404, body=""))
    page.route(re.compile(r".*/data/.*\.timing\.json"), lambda r: r.fulfill(json=PASSAGES[re.search(r"/data/(.*)\.timing", r.request.url).group(1)]))
    page.route(re.compile(r".*/api/.*"), lambda r: r.fulfill(json={"ok": True, "data": []}))
    page.route(re.compile(r".*/api/read-aloud/settings"), lambda r: r.fulfill(json={"success": True, "data": {"defaults": {"mic": True, "share": True, "readers": False}, "classes": []}}))
    page.goto(f"{BASE}#/read/{pid}")
    page.wait_for_selector("#w-0")
    return page


def start_reading(page):
    page.get_by_role("button", name="Read aloud with the mic").click()
    agree = page.get_by_role("button", name="I agree, continue")
    if agree.count():
        agree.click()
    page.get_by_role("button", name="Start reading").click()
    page.wait_for_function("window.__recs.length >= 1 && window.__recs[window.__recs.length - 1].started")


def say(page, text):
    page.evaluate("t => window.__say([[t, true]])", text)


def listening_again(page, count):
    page.wait_for_function(f"window.__recs.length === {count} && window.__recs[{count - 1}].started", timeout=8000)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


handler = functools.partial(Quiet, directory=str(DIST))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
BASE = f"http://127.0.0.1:{server.server_port}/"
threading.Thread(target=server.serve_forever, daemon=True).start()

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 390, "height": 800})  # phone width
    page = open_reader(ctx, "p-en")
    start_reading(page)
    say(page, "I like it it is fun today")
    page.wait_for_selector(".callout")
    check("a skipped word offers Help me say it", page.get_by_role("button", name="Help me say it").is_visible())
    check("no help panel until asked", page.locator("#pron-help").count() == 0)

    help_btn = page.get_by_role("button", name="Help me say it")
    help_btn.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#pron-help .syl")
    check("help opens from the keyboard and focus moves into it", page.evaluate("document.activeElement.id") == "pron-h")
    check("the word is shown in syllables", page.locator("#pron-help .syl").all_inner_texts() == ["be", "cause"], str(page.locator("#pron-help .syl").all_inner_texts()))
    check("syllables are announced as text", "Syllables: because: be, cause" in (page.locator("#pron-help .syllables").get_attribute("aria-label") or ""))
    check("no page-wide horizontal scroll at phone width", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
    axe_clean(page, "help open")

    page.get_by_role("button", name="Hear it slowly").click()
    page.wait_for_function("window.__rates.includes(0.4)")
    check("Hear it slowly plays at 0.4 speed", page.evaluate("window.__rates.includes(0.4)"))
    page.wait_for_function("window.__rates[window.__rates.length - 1] === 1", timeout=5000)
    check("the learner's own speed is put back afterwards", page.evaluate("window.__rates[window.__rates.length - 1]") == 1)
    check("pitch is kept", page.evaluate("document.querySelector('audio').preservesPitch") is True)

    # success path
    recs_before = page.evaluate("window.__recs.length")
    page.get_by_role("button", name="Say it with me").click()
    check("the microphone stays off while the word is played slowly", page.evaluate("window.__recs.length") == recs_before)
    listening_again(page, recs_before + 1)
    check("then it listens for the word", "Say “because”" in page.locator("#pron-help .msg").inner_text(), page.locator("#pron-help .msg").inner_text())
    page.evaluate("window.__say([['because', true]])")
    page.wait_for_selector("#pron-help .msg.good")
    check("success is celebrated gently", "Nicely said" in page.locator("#pron-help .msg").inner_text())
    check("the microphone is released after success", page.evaluate("window.__recs[window.__recs.length - 1].stopped") is True)
    axe_clean(page, "help success")

    # retry path: one miss, one more try, success
    n = page.evaluate("window.__recs.length")
    page.get_by_role("button", name="Say it with me").click()
    listening_again(page, n + 1)
    page.evaluate("window.__say([['banana', true]])")
    page.get_by_role("button", name="Try once more").wait_for()
    check("a miss gives a gentle second chance", "Almost there" in page.locator("#pron-help .msg").inner_text())
    page.get_by_role("button", name="Try once more").click()
    listening_again(page, n + 2)
    page.evaluate("window.__say([['because', true]])")
    page.wait_for_selector("#pron-help .msg.good")
    check("the second try can succeed", True)

    # two misses: invited to carry on, never stuck
    n = page.evaluate("window.__recs.length")
    page.get_by_role("button", name="Say it with me").click()
    listening_again(page, n + 1)
    page.evaluate("window.__say([['banana', true]])")
    page.get_by_role("button", name="Try once more").click()
    listening_again(page, n + 2)
    page.evaluate("window.__say([['window', true]])")
    page.wait_for_function("document.querySelector('#pron-help .msg').textContent.includes('tricky')")
    check("after two misses the learner is invited to carry on", page.get_by_role("button", name="Read from here").is_visible())

    # My words
    add = page.get_by_role("button", name="Add to My words")
    add.click()
    check("Add to My words toggles on", page.get_by_role("button", name="In My words").get_attribute("aria-pressed") == "true")
    saved = json.loads(page.evaluate("localStorage.getItem('soundalong.practice.v1.p-en')"))
    check("the word is saved on this device", "because" in saved["words"], json.dumps(saved))
    page.keyboard.press("Escape")
    check("Escape closes the help and focus returns to its button", page.evaluate("document.activeElement.textContent.trim()") == "Help me say it")
    page.goto(f"{BASE}#/practice/p-en")
    page.wait_for_selector("text=My words")
    check("the word shows in Practice", "1 saved" in page.locator("body").inner_text())
    page.get_by_role("button", name="Show answer").click()
    check("the flashcard is the flagged word", page.locator(".answer").inner_text().strip() == "because")
    page.close()

    # End summary: Words to practice and add all (fresh storage)
    ctx2 = browser.new_context(viewport={"width": 390, "height": 800})
    p2 = open_reader(ctx2, "p-en")
    start_reading(p2)
    say(p2, "I like it it is fun today")
    p2.wait_for_selector(".callout")
    p2.get_by_role("button", name="Read from here").click()
    listening_again(p2, 2)
    say(p2, "I like it because it is today")
    p2.wait_for_selector(".callout")
    check("a second word is flagged", "fun" in p2.locator(".callout .msg").inner_text())
    p2.get_by_role("button", name="Read from here").click()
    listening_again(p2, 3)
    say(p2, "I like it because it is fun today")
    p2.wait_for_selector("text=Well done")
    check("the summary lists Words to practice", p2.locator("#pw-h").inner_text() == "Words to practice" and p2.locator(".chips li").all_inner_texts() == ["because", "fun"], str(p2.locator(".chips li").all_inner_texts()))
    axe_clean(p2, "words to practice")
    p2.get_by_role("button", name="Add all 2 to My words").click()
    saved = json.loads(p2.evaluate("localStorage.getItem('soundalong.practice.v1.p-en')"))
    check("add all saves every flagged word", sorted(saved["words"]) == ["because", "fun"], json.dumps(saved))
    check("add all confirms in words and keeps focus", "added to My words" in p2.evaluate("document.activeElement.textContent"))
    p2.close()

    # Spanish: syllables with the right language
    es = open_reader(ctx2, "p-es")
    start_reading(es)
    say(es, "el nino esta muy hoy")
    es.wait_for_selector(".callout")
    es.get_by_role("button", name="Help me say it").click()
    es.wait_for_selector("#pron-help .syl")
    check("Spanish syllables", es.locator("#pron-help .syl").all_inner_texts() == ["can", "sa", "do"], str(es.locator("#pron-help .syl").all_inner_texts()))
    check("Spanish word is labelled as Spanish", es.locator("#pron-help .syllables").get_attribute("lang") == "es")
    es.close()

    # Estimated timing: no slow audio, but the rest still works
    est = open_reader(ctx2, "p-est")
    start_reading(est)
    say(est, "I like it it is fun today")
    est.wait_for_selector(".callout")
    check("no Hear it for estimated timing", est.get_by_role("button", name="Hear it", exact=True).count() == 0)
    est.get_by_role("button", name="Help me say it").click()
    est.wait_for_selector("#pron-help .syl")
    check("no Hear it slowly for estimated timing", est.get_by_role("button", name="Hear it slowly").count() == 0)
    n = est.evaluate("window.__recs.length")
    est.get_by_role("button", name="Say it with me").click()
    listening_again(est, n + 1)
    check("Say it with me skips the slow step and listens at once", True)
    est.close()
    browser.close()

server.shutdown()
print("\nFAILED: " + ", ".join(failures) if failures else "\nAll steps passed.")
sys.exit(1 if failures else 0)
