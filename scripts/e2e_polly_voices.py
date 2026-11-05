"""Browser check for Amazon Polly voices in Settings, with STUB API answers (no AWS, no network).

It serves web/dist (run `cd web && npm run build` first), answers /api/settings itself, and checks: with Polly selected the English and Spanish menus list the
Polly voices and are enabled; picking a voice marks the form dirty and saves the VoiceId; the sample button plays a sample or says it is not available yet;
switching to the built-in voices swaps the menus; the voice quality choice is saved; phone width has no horizontal scroll. Optional accessibility check:
set AXE_JS to the path of axe-core's axe.min.js (for example /Users/Rohan.Athmakuri/Downloads/OI-Starship/OI-Starship-UI/node_modules/axe-core/axe.min.js).

Usage: python3 scripts/e2e_polly_voices.py        (exit code 0 only when every step passes; uses real Chrome through playwright channel="chrome")
"""
import functools, http.server, json, os, pathlib, re, sys, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
AXE = os.environ.get("AXE_JS", "")
SAMPLE_MP3 = (ROOT / "web" / "public" / "voice-samples" / "af_heart.mp3").read_bytes()  # any real mp3 stands in for a Polly sample
AVAILABLE_SAMPLES = {"polly-Ruth.mp3", "polly-Joanna.mp3"}  # every other Polly sample answers 404, as before the samples are built

VOICES = [
    {"id": "af_heart", "label": "Heart (US female)", "lang": "en", "engine": "kokoro", "recommended": True},
    {"id": "phonon_hadley", "label": "Hadley (US female, even-toned and kind)", "lang": "en", "engine": "phonon", "recommended": True},
    {"id": "ef_dora", "label": "Dora (Spanish female)", "lang": "es", "engine": "kokoro", "recommended": True},
    {"id": "Joanna", "label": "Joanna (US female)", "lang": "en", "accent": "en-US", "engine": "polly", "engines": ["neural", "generative"], "recommended": False},
    {"id": "Ruth", "label": "Ruth (US female)", "lang": "en", "accent": "en-US", "engine": "polly", "engines": ["neural", "generative"], "recommended": False},
    {"id": "Matthew", "label": "Matthew (US male)", "lang": "en", "accent": "en-US", "engine": "polly", "engines": ["neural", "generative"], "recommended": False},
    {"id": "Lupe", "label": "Lupe (US Spanish female)", "lang": "es", "accent": "es-US", "engine": "polly", "engines": ["neural", "generative"], "recommended": False},
    {"id": "Mia", "label": "Mia (Mexican Spanish female)", "lang": "es", "accent": "es-MX", "engine": "polly", "engines": ["neural", "generative"], "recommended": False},
]
DEFAULTS = {"kokoro": {"voice": "af_heart", "voiceEs": "ef_dora"}, "polly": {"voice": "Joanna", "voiceEs": "Lupe"}}
state = {"settings": {"voice": "Joanna", "voiceEs": "Lupe", "speed": 0.95, "mp3Kbps": 48, "ttsEngine": "polly"}, "puts": []}
failures = []
PLAY_SPY = """
window.__played = [];
const realPlay = HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play = function () { window.__played.push(this.src); return realPlay.call(this); };
"""


def view():
    return {**state["settings"], "pollyEngine": state["settings"].get("pollyEngine", "neural"), "voices": VOICES, "voiceDefaults": DEFAULTS}


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


def on_settings(route):
    request = route.request
    if request.method == "PUT":
        body = json.loads(request.post_data or "{}")
        state["puts"].append(body)
        state["settings"] = {**state["settings"], **body}
        return route.fulfill(json={"success": True, "data": view()})
    route.fulfill(json={"success": True, "data": view()})


def on_sample(route):
    name = route.request.url.rsplit("/", 1)[-1]
    if name in AVAILABLE_SAMPLES:
        return route.fulfill(status=200, body=SAMPLE_MP3, headers={"content-type": "audio/mpeg"})
    route.fulfill(status=404, body="")


def open_settings(ctx, width=1100):
    page = ctx.new_page()
    page.set_viewport_size({"width": width, "height": 900})
    page.add_init_script(PLAY_SPY)
    page.route(re.compile(r".*/voice-samples/.*\.mp3"), on_sample)
    page.route(re.compile(r".*/api/.*"), lambda r: r.fulfill(json={"success": True, "data": []}))
    page.route(re.compile(r".*/api/settings$"), on_settings)
    page.goto(BASE + "#/settings")
    page.wait_for_selector("#s-voice")
    return page


def options(page, selector):
    return page.eval_on_selector_all(selector + " option", "els => els.map(e => e.value)")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST)))
BASE = f"http://127.0.0.1:{server.server_port}/"
threading.Thread(target=server.serve_forever, daemon=True).start()

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 1100, "height": 900})
    page = open_settings(ctx)

    check("Polly is the selected engine", page.get_by_label("Amazon Polly").is_checked())
    check("the English menu lists the Polly voices only", options(page, "#s-voice") == ["Joanna", "Ruth", "Matthew"], str(options(page, "#s-voice")))
    check("the Spanish menu lists the Polly voices only", options(page, "#s-voice-es") == ["Lupe", "Mia"], str(options(page, "#s-voice-es")))
    check("the menus are enabled and not greyed out", page.locator("#s-voice").is_enabled() and page.locator("#s-voice-es").is_enabled()
          and page.evaluate("getComputedStyle(document.querySelector('#s-voice').closest('.field')).opacity") == "1")
    check("with nothing recommended yet there is no claim of quality", page.locator("#s-voice optgroup").first.get_attribute("label") == "Voices" and "listening test" not in page.inner_text("form"))
    check("no internal engine names are shown", not re.search(r"Kokoro|Phonon|Lambda|Whisper", page.inner_text("form")))
    check("nothing to save before a change", page.get_by_role("button", name="Save settings").is_disabled())
    axe_clean(page, "Settings with Polly voices")

    page.select_option("#s-voice", "Ruth")
    check("picking a voice makes the form dirty", page.get_by_role("button", name="Save settings").is_enabled())
    page.wait_for_function("window.__played.some(s => s.endsWith('polly-Ruth.mp3'))")
    check("choosing a voice plays its sample (polly-<VoiceId>.mp3)", True)
    page.wait_for_timeout(200)
    check("an available sample shows no 'not available' note", page.get_by_text("Sample not available yet").count() == 0)
    page.select_option("#s-voice-es", "Mia")
    page.wait_for_selector("text=Sample not available yet")
    check("a missing sample says so calmly, with no error text", page.get_by_text("Sample not available yet").is_visible() and page.get_by_role("alert").count() == 0)
    axe_clean(page, "sample not available note")
    page.get_by_role("button", name="Save settings").click()
    page.wait_for_selector("text=Settings saved")
    check("saving sends the Polly VoiceIds", state["puts"] and state["puts"][-1]["voice"] == "Ruth" and state["puts"][-1]["voiceEs"] == "Mia" and state["puts"][-1]["ttsEngine"] == "polly", str(state["puts"]))
    check("the form is clean again after saving", page.get_by_role("button", name="Save settings").is_disabled())

    page.get_by_role("button", name="Play Ruth (US female) sample").click()
    page.wait_for_timeout(300)
    check("Hear it plays the sample of the selected voice again", sum(s.endswith("polly-Ruth.mp3") for s in page.evaluate("window.__played")) >= 2, str(page.evaluate("window.__played")))

    page.get_by_label("Most natural (generative)").check()
    check("voice quality is offered with Polly and marks the form dirty", page.get_by_role("button", name="Save settings").is_enabled())
    page.get_by_role("button", name="Save settings").click()
    page.wait_for_selector("text=Settings saved")
    check("the voice quality is saved", state["puts"][-1].get("pollyEngine") == "generative", str(state["puts"][-1]))

    page.get_by_label("Built-in voices").check()
    check("built-in voices swap the menus to the open-source voices", options(page, "#s-voice") == ["af_heart", "phonon_hadley"] and options(page, "#s-voice-es") == ["ef_dora"], str(options(page, "#s-voice")))
    check("the voice quality choice is hidden for built-in voices", page.get_by_label("Most natural (generative)").count() == 0)
    check("the selection moved to the built-in defaults", page.input_value("#s-voice") == "af_heart" and page.input_value("#s-voice-es") == "ef_dora")
    page.get_by_label("Amazon Polly").check()
    check("switching back to Polly restores Polly defaults", page.input_value("#s-voice") == "Joanna" and page.input_value("#s-voice-es") == "Lupe", page.input_value("#s-voice"))
    page.close()

    # An old saved open-source voice while Polly is the engine: the API (stubbed here as the real one answers) returns the deployment default.
    state["settings"] = {**state["settings"], "voice": "Joanna", "voiceEs": "Lupe", "ttsEngine": "polly"}
    phone = open_settings(ctx, width=375)
    check("phone width: no horizontal scroll", phone.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), str(phone.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")))
    check("phone width: the menus fit the screen", phone.evaluate("[...document.querySelectorAll('select')].every(s => s.getBoundingClientRect().right <= innerWidth)"))
    axe_clean(phone, "Settings at phone width")
    phone.close()
    browser.close()

server.shutdown()
print("\nFAILED: " + ", ".join(failures) if failures else "\nAll steps passed.")
sys.exit(1 if failures else 0)
