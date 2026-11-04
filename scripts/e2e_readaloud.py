"""Browser check for "Read aloud with the microphone", with a FAKE speech recognizer (no real microphone, no network).

It serves web/dist (run `cd web && npm run build` first), answers the passage and API requests itself, replaces SpeechRecognition with a
scripted fake, and walks the flow: the short speech-service line (no consent screen), following, a skipped word, Hear it, Read from here, finishing, saved results, Spanish, and a
browser without speech recognition. Optional accessibility check: set AXE_JS to the path of axe-core's axe.min.js.

Usage: python3 scripts/e2e_readaloud.py        (exit code 0 only when every step passes)
"""
import functools, http.server, json, os, pathlib, re, sys, threading
from playwright.sync_api import sync_playwright

DIST = pathlib.Path(__file__).resolve().parent.parent / "web" / "dist"
AXE = os.environ.get("AXE_JS", "")


def passage(text, lang):
    words, t = [], 0
    for i, w in enumerate(text.split()):
        words.append({"i": i, "text": w, "start_ms": t, "end_ms": t + 350, "aligned": True, "sentence": 0, "paragraph": 0})
        t += 400
    return {"id": "p-" + lang, "title": "Test passage", "language": lang, "engine": "polly", "duration_ms": t, "words": words}


PASSAGES = {
    "p-en": passage("I like it because it is fun today.", "en"),
    "p-es": passage("El niño está muy cansado hoy.", "es"),
}
FAKE = """
window.__recs = [];
window.SpeechRecognition = class { constructor() { this.stopped = false; window.__recs.push(this); }
  start() { this.started = true; setTimeout(() => this.onstart && this.onstart(), 0); }
  stop() { this.stopped = true; setTimeout(() => this.onend && this.onend(), 0); } };
window.__say = (items) => { const r = window.__recs[window.__recs.length - 1];
  r.onresult({ resultIndex: 0, results: items.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f })) }); };
"""

failures = []
SETTINGS = {"defaults": {"mic": True, "share": True, "readers": False}, "classes": []}


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def axe_clean(page, name):
    if not AXE:
        print("SKIP  axe: " + name + " (set AXE_JS)")
        return
    page.add_script_tag(path=AXE)
    result = page.evaluate("axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa'] }).then(r => r.violations.map(v => v.id + ': ' + v.nodes.length))")
    check("axe clean: " + name, result == [], str(result))


def open_reader(ctx, pid, speech=True, mode="stop"):
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('soundalong.readAloudMode.v1', '%s');" % mode)
    page.add_init_script(FAKE if speech else "delete window.SpeechRecognition; delete window.webkitSpeechRecognition;")
    page.route(re.compile(r".*/data/.*\.(mp3|json)$"), lambda r: r.fulfill(status=404, body=""))
    page.route(re.compile(r".*/data/.*\.timing\.json"), lambda r: r.fulfill(json=PASSAGES[re.search(r"/data/(.*)\.timing", r.request.url).group(1)]))
    page.route(re.compile(r".*/api/.*"), lambda r: r.fulfill(json={"ok": True, "data": []}))
    page.route(re.compile(r".*/api/read-aloud/settings"), lambda r: r.fulfill(json={"success": True, "data": SETTINGS}))
    page.goto(f"{BASE}#/read/{pid}")
    page.wait_for_selector("#w-0")
    if speech:
        page.wait_for_selector("text=Read aloud with the mic")  # the teacher's switch has loaded
    return page


def marks(page):
    return page.evaluate("[...document.querySelectorAll('.w')].map(e => e.dataset.ra || '-').join(',')")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


handler = functools.partial(Quiet, directory=str(DIST))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
BASE = f"http://127.0.0.1:{server.server_port}/"
threading.Thread(target=server.serve_forever, daemon=True).start()

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 1100, "height": 900})
    page = open_reader(ctx, "p-en")

    btn = page.get_by_role("button", name="Read aloud with the mic")
    check("button is shown when speech recognition exists", btn.count() == 1)
    btn.focus(); page.keyboard.press("Enter")
    check("keyboard opens the panel and there is no consent screen", page.get_by_role("button", name="Start reading").is_visible() and page.get_by_role("button", name="I agree, continue").count() == 0)
    check("a short line says the browser's speech service listens", "speech service listens" in page.locator("section.ra").inner_text())
    check("nothing started before Start reading", page.evaluate("window.__recs.length") == 0)
    axe_clean(page, "panel")
    page.get_by_role("button", name="Start reading").click()
    page.wait_for_function("window.__recs.length === 1 && window.__recs[0].started")
    check("recognizer listens in the passage language", page.evaluate("window.__recs[0].lang") == "en-US")

    page.evaluate("window.__say([['I like', false]])")
    check("follows word by word", marks(page).startswith("read,read,next"), marks(page))
    page.wait_for_timeout(300)  # the highlight fades in over a moment
    bg = page.evaluate("getComputedStyle(document.querySelector('.passage .w[data-ra=read]')).backgroundColor")
    check("words already read are highlighted in yellow", bg == "rgb(251, 231, 161)", bg)
    page.evaluate("window.__say([['I like it it is fun today', true]])")
    page.wait_for_selector(".callout")
    check("a skipped word stops with a plain message", "You skipped" in page.locator(".callout .msg").inner_text() and "because" in page.locator(".callout .msg").inner_text())
    check("skipped word is marked", page.locator('#w-3[data-ra="skipped"]').count() == 1)
    check("microphone stopped while the learner is guided back", page.evaluate("window.__recs[0].stopped") is True)
    check("focus moves to Read from here", page.evaluate("document.activeElement.textContent.trim()") == "Read from here")
    check("Hear it is offered (the word has trusted timing)", page.get_by_role("button", name="Hear it").is_visible())
    axe_clean(page, "skipped callout")
    page.get_by_role("button", name="Hear it").click()
    check("Hear it selects that word", page.locator("#w-3").is_visible())
    page.get_by_role("button", name="Read from here").click()
    page.wait_for_function("window.__recs.length === 2 && window.__recs[1].started")
    check("restarts at the sentence start with a new session", marks(page).startswith("next"), marks(page))
    page.evaluate("window.__say([['I like it because it is fun today', true]])")
    page.wait_for_selector("text=Well done")
    check("finishing shows a summary", page.locator(".summary").inner_text().replace("\n", " ").find("8 of 8") >= 0, page.locator(".summary").inner_text())
    saved = json.loads(page.evaluate("localStorage.getItem('soundalong.readaloud.v1.p-en')"))
    check("results are saved as counts only", saved["sessions"][0] == {**saved["sessions"][0], "read": 8, "skipped": 1, "retried": 1} and "because" not in json.dumps(saved), json.dumps(saved))
    axe_clean(page, "summary")
    page.get_by_role("button", name="Clear my reading results").click() if page.get_by_role("button", name="Clear my reading results").count() else None
    page.get_by_role("button", name="Close").first.click()
    check("closing returns focus to the Read aloud button", page.evaluate("document.activeElement.textContent.includes('Read aloud with the mic')"))
    check("marks are removed on close", set(marks(page).split(",")) == {"-"})
    page.close()

    es = open_reader(ctx, "p-es")
    es.get_by_role("button", name="Read aloud with the mic").click()
    es.get_by_role("button", name="Start reading").click()
    es.wait_for_function("window.__recs.length === 1")
    check("Spanish passage listens in Spanish", es.evaluate("window.__recs[0].lang") == "es-US")
    es.evaluate("window.__say([['el nino esta muy cansado hoy', true]])")
    es.wait_for_selector("text=Well done")
    check("Spanish accents are forgiven", True)
    es.close()

    # ---- "keep going" (the default): a missed word does not stop the reading
    ctx2 = browser.new_context(viewport={"width": 1100, "height": 900})
    keep = open_reader(ctx2, "p-en", mode="keepGoing")
    keep.get_by_role("button", name="Read aloud with the mic").click()
    check("the panel offers both ways of reacting to a missed word", keep.get_by_label("Keep going and remind me").is_checked() and keep.get_by_label("Stop and guide me back").count() == 1)
    keep.get_by_role("button", name="Start reading").click()
    keep.wait_for_function("window.__recs.length === 1 && window.__recs[0].started")
    keep.evaluate("window.__say([['I like it it is fun', true]])")
    keep.wait_for_selector("[data-testid=ra-nudge]")
    check("a calm reminder names the missed word", "You missed" in keep.locator("[data-testid=ra-nudge]").inner_text() and "because" in keep.locator("[data-testid=ra-nudge]").inner_text())
    check("no stop: the microphone keeps listening and there is no callout", keep.evaluate("window.__recs[0].stopped") is False and keep.locator(".callout").count() == 0)
    check("the missed word stays marked while reading goes on", "skipped" in marks(keep).split(","))
    axe_clean(keep, "reminder")
    keep.evaluate("window.__say([['I like it it is fun today', true]])")
    keep.wait_for_selector("text=Well done")
    check("reading carried on to the end, and the summary counts the miss", "1" in keep.locator(".summary").inner_text())
    keep.get_by_role("button", name="Read again").click()
    keep.wait_for_function("window.__recs.length >= 2")
    keep.evaluate("window.__say([['I like it it is fun', true]])")  # not the last word yet, so the reminder stays visible
    keep.wait_for_selector("[data-testid=ra-nudge]")
    keep.get_by_role("button", name="Go back").click()
    check("Go back clears the reminder and restarts at that sentence", keep.locator("[data-testid=ra-nudge]").count() == 0 and marks(keep).split(",")[0] in ("next", "read"), marks(keep))
    ctx2.close()

    plain = open_reader(ctx, "p-en", speech=False)
    check("button is hidden when the browser has no speech recognition", plain.get_by_role("button", name="Read aloud with the mic").count() == 0)
    plain.close()
    browser.close()

server.shutdown()
print("\nFAILED: " + ", ".join(failures) if failures else "\nAll steps passed.")
sys.exit(1 if failures else 0)
