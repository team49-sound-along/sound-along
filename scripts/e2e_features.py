"""Feature-by-feature end-to-end checks (cards, pictures, places, figures, quiz, long documents, keyboard, highlight modes, privacy, recording variant,
review and regenerate, hostile input, busy generator, deep links, offline errors, student view, audio-off assignment).
Usage (on SCRATCH copies of data/): python3 scripts/e2e_features.py <server url> <server url that has a long document> <data dir of the first server>"""
import json, re, sys, time, traceback, urllib.request
from playwright.sync_api import sync_playwright
BASE = sys.argv[1].rstrip("/") + "/"; SERIES = sys.argv[2].rstrip("/") + "/"; DATA = sys.argv[3]
PARK = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"; TEA = "5af24980-4d6d-41c1-87fa-4f21cb2d169d"; DAY = "457244d4-8d08-57cb-aa31-ace6ed9dac04"
results = []; problems = []
def step(name, fn):
    try:
        r = fn(); ok = r is None or r is True
    except Exception as e:
        ok, r = False, f"{type(e).__name__}: {str(e).splitlines()[0][:170]}"
    results.append(ok); print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" — {r}"), flush=True)
api = lambda base, p, body=None: json.load(urllib.request.urlopen(urllib.request.Request(base + "api/" + p, data=json.dumps(body).encode() if body is not None else None, headers={"content-type": "application/json"}))) 
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: problems.append("pageerror " + str(e)[:150]))
    reqs = []; pg.on("request", lambda r: reqs.append((r.method, r.url)))
    go = lambda h, base=None: (pg.goto((base or BASE) + h), pg.wait_for_timeout(900))
    def reader(pid, base=None): go(f"#/read/{pid}", base); pg.reload(); pg.wait_for_selector(".w"); pg.wait_for_timeout(600)

    # ---- cards, pictures, places, figures
    def pictures():
        reader(TEA); pg.locator(".w.haspic").first.click(); pg.wait_for_timeout(700)
        ok = pg.evaluate("(()=>{const i=document.querySelector('.wpic img');return !!i&&i.complete&&i.naturalWidth>20})()")
        credit = pg.locator(".wpic figcaption").count()
        return (ok and credit == 1) or f"picture loaded={ok} credit={credit}"
    step("word picture: loads, has a credit line", pictures)
    def place():
        reader(PARK); w = pg.locator(".w", has_text=re.compile("Piedmont")).first; w.click(); pg.wait_for_timeout(900)
        card = pg.locator("[aria-label='Place card']")
        if card.count() != 1: return "no place card"
        img = pg.evaluate("(()=>{const i=document.querySelector(\"[aria-label='Place card'] img\");return !i||(i.complete&&i.naturalWidth>20)})()")
        return (len(card.inner_text()) > 40 and img) or "place card empty or picture broken"
    step("place card for 'Piedmont Park': text and picture", place)
    def figure():
        reader(TEA); ok = pg.evaluate("(()=>{const i=document.querySelector('.fig img');return !!i&&i.complete&&i.naturalWidth>50})()")
        return ok or "no figure image rendered between paragraphs"
    step("original passage figure renders", figure)
    def defcards():
        reader(PARK); n = pg.locator(".w.vocab").count()
        pg.locator(".w.vocab").first.click(); pg.wait_for_timeout(500)
        t = pg.locator("[aria-label='Word help'] .def").inner_text() if pg.locator("[aria-label='Word help'] .def").count() else ""
        return (n >= 10 and len(t) > 10) or f"{n} defined words, definition '{t[:30]}'"
    step("vocabulary words are underlined and show a definition", defcards)

    # ---- quiz
    def quiz():
        go(f"#/practice/{PARK}"); pg.wait_for_selector("text=Practice questions", timeout=8000)
        ch = pg.locator(".qchoices button"); n = ch.count()
        if n < 2: return f"{n} choices"
        ch.first.click(); pg.wait_for_timeout(300)
        if not re.search(r"correct|your choice", pg.inner_text(".qchoices")): return "no feedback"
        if any(not x.is_disabled() for x in ch.all()): return "choices still enabled after answering"
        pg.get_by_role("button", name="Next question").click(); pg.wait_for_timeout(300)
        return pg.locator(".qchoices button:not([disabled])").count() >= 2 or "next question did not reset"
    step("practice questions: answer, feedback, next question", quiz)
    step("passages with no approved questions show no quiz", lambda: (go(f"#/practice/{TEA}"), pg.locator("text=Practice questions").count() == 0 or "quiz shown without approval")[1])

    # ---- keyboard, highlight modes, phrase breaks
    def keys():
        reader(PARK); pg.locator(".w").nth(0).focus(); pg.keyboard.press("Home"); [pg.keyboard.press("ArrowRight") for _ in range(3)]
        f = pg.evaluate("document.activeElement.id")
        if f != "w-3": return f"ArrowRight x3 landed on {f}"
        pg.keyboard.press("Home"); f = pg.evaluate("document.activeElement.id")
        if f != "w-0": return f"Home {f}"
        pg.keyboard.press("End"); f = pg.evaluate("document.activeElement.id")
        if not f.startswith("w-") or int(f[2:]) < 300: return f"End {f}"
        pg.keyboard.press("Home"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
        if pg.evaluate("document.querySelector('audio').currentTime") <= 0 or pg.evaluate("document.querySelector('audio').paused"): return "Enter did not play"
        pg.evaluate("document.querySelector('audio').pause()"); pg.locator(".w").nth(10).focus(); t0 = pg.evaluate("document.querySelector('audio').currentTime"); pg.keyboard.press("h"); pg.wait_for_timeout(500)
        return pg.evaluate("document.querySelector('audio').currentTime") != t0 or "H did not play the word"
    step("keyboard: arrows, Home/End, Enter plays, H hears the word", keys)
    def highlight_modes():
        reader(PARK); pg.get_by_role("button", name="Reading settings").click(); P = pg.locator("#reading-settings")
        out = {}
        for mode in ("Words", "Sentences", "Off"):
            P.get_by_label(mode, exact=True).check(); pg.evaluate("a=document.querySelector('audio');a.currentTime=20;a.play()"); pg.wait_for_timeout(900)
            out[mode] = (pg.locator(".w.active").count(), pg.locator(".w.band").count()); pg.evaluate("document.querySelector('audio').pause()")
        P.get_by_label("Words", exact=True).check()
        return (out["Words"][0] == 1 and out["Sentences"][0] == 0 and out["Sentences"][1] > 3 and out["Off"] == (0, 0)) or out
    step("highlight modes: one word / the sentence / none", highlight_modes)
    def phrase():
        reader(PARK); a = pg.evaluate("document.querySelectorAll('.passage .line, .passage p').length")
        pg.get_by_role("button", name="Reading settings").click(); pg.locator("#reading-settings").get_by_role("switch", name="Line breaks at phrases").click(); pg.wait_for_timeout(300)
        b2 = pg.evaluate("document.querySelectorAll('.passage .line, .passage p').length")
        pg.locator("#reading-settings").get_by_role("switch", name="Line breaks at phrases").click()
        return b2 != a or f"lines {a}->{b2}"
    step("phrase line breaks change the layout", phrase)

    # ---- privacy of practice
    def privacy():
        bodies = []; pg.on("request", lambda r: bodies.append((r.method, r.url, r.post_data or "")) if r.method != "GET" else None)
        reader(PARK); pg.locator(".w").nth(12).click(); pg.get_by_role("button", name=re.compile("^. Save word")).click(); pg.locator("button[aria-label^=Pause]").click()
        pg.wait_for_timeout(400); bodies.clear()
        pg.get_by_role("link", name="Practice").first.click(); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Show answer").click(); pg.get_by_role("button", name=re.compile("knew")).click(); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="Clear my words").click(); pg.get_by_role("button", name="Yes, clear them").click(); pg.wait_for_timeout(300)
        return not bodies or f"network writes from the practice screen: {bodies[:3]}"
    step("practice screen sends nothing over the network (no POST/PUT of saved words or answers)", privacy)
    def event_payloads():
        seen = []; pg.on("request", lambda r: seen.append(r.post_data or "") if r.url.endswith("/api/events") else None)
        reader(PARK); w = re.sub(r"\W", "", pg.locator(".w").nth(20).inner_text()).lower(); pg.locator(".w").nth(20).click(); pg.wait_for_timeout(700)
        pg.locator("button[aria-label^=Pause]").click() if pg.locator("button[aria-label^=Pause]").count() else None
        bad = [p for p in seen if (len(w) > 2 and w in p.lower()) or not re.fullmatch(r'\{"passageId":"[0-9a-f-]{36}","type":"[a-z_]+"(,"classId":"[^"]+")?\}', p)]
        return (seen and not bad) or f"events {len(seen)}; unexpected payloads: {bad[:2]}"
    step("analytics events carry only passage id, event type and class (never a word or a person)", event_payloads)

    # ---- a long document is ONE passage, on the second server (which holds one made from a long upload)
    def one_passage():
        passages = api(SERIES, "passages")["data"]
        parts = [p for p in passages if p.get("series") or re.search(r"\((?:Part|Parte) \d+ (?:of|de) \d+\)", p["title"])]
        if parts: return f"{len(parts)} passage(s) still look like parts of a document: {parts[0]['title']}"
        long = sorted((p for p in passages if p["words"] > 1000 and p["language"] == "en" and not p.get("translationOf")), key=lambda p: -p["words"])
        if not long: return "no long passage on the second server to check"
        go("#/library", SERIES); pg.wait_for_selector(".pcard"); text = pg.inner_text("main")
        if re.search(r"\bParts?\b|parts", text): return "the Library mentions parts"
        pg.goto(SERIES + f"#/read/{long[0]['id']}"); pg.wait_for_selector(".w"); pg.wait_for_timeout(1000)
        if re.search(r"\bParts?\b|Next part", pg.inner_text("main")): return "the reader mentions parts"
        t = json.load(urllib.request.urlopen(SERIES + f"data/{long[0]['id']}.timing.json"))
        w = t["words"]
        if not all(w[k]["start_ms"] <= w[k + 1]["start_ms"] for k in range(len(w) - 1)): return "word times are not in order"
        pg.locator("button[aria-label=Play]").click(); pg.wait_for_timeout(1500)
        pg.locator(".w").nth(len(w) - 5).click(); pg.wait_for_timeout(800)  # tap near the very end of the long passage: one audio, one timeline
        now = pg.evaluate("document.querySelector('audio').currentTime")
        return abs(now - w[len(w) - 5]["start_ms"] / 1000) < 1.5 or f"tapping the end played {now}s, the word is at {w[len(w) - 5]['start_ms'] / 1000}s"
    step("long document: one passage, no parts anywhere, one audio and timeline from start to end", one_passage)

    # ---- student view
    def student_reader():
        reader(PARK); pg.get_by_role("radio", name="Student").click(); pg.wait_for_timeout(400)
        t = pg.inner_text("main"); pg.get_by_role("radio", name="Teacher").click()
        return not re.search(r"computer-generated|Human narration|Kokoro|Polly|engine", t, re.I) or "student sees voice/engine information"
    step("student reader shows no voice/engine internals", student_reader)
    def audio_off():
        a = api(BASE, "assignments", {"passageId": PARK, "classId": "cls-g3-p2", "soundAlong": False})["data"]
        pg.goto(BASE + "#/library"); pg.get_by_role("radio", name="Student").click(); pg.wait_for_timeout(300)
        pg.goto(BASE + f"#/read/{PARK}"); pg.wait_for_selector(".w"); pg.wait_for_timeout(800)
        # the reader decides from the assignment list; open it through My assignments like a student would
        pg.goto(BASE + "#/assignments"); pg.wait_for_timeout(900)
        card = pg.locator(".cards .card", has_text="Text only")
        if card.count() < 1: pg.get_by_role("radio", name="Teacher").click(); return "no 'Text only' assignment card"
        card.first.get_by_role("link", name="Open").click(); pg.wait_for_timeout(1200)
        has_audio = pg.locator("audio").count(); note = "Audio is off" in pg.inner_text("main")
        pg.locator(".w").first.click(); pg.wait_for_timeout(300)
        pg.get_by_role("radio", name="Teacher").click() if pg.get_by_role("radio", name="Teacher").count() else None
        return (has_audio == 0 and note) or f"audio elements {has_audio}, note {note}"
    step("assignment with Sound Along off: text only, no audio, clear note", audio_off)

    # ---- deep links, history
    def deeplinks():
        pg.goto(BASE + "#/library"); pg.goto(BASE + f"#/read/{PARK}?s=6&play=1"); pg.reload(); pg.wait_for_selector(".w"); pg.wait_for_timeout(2500)
        act = pg.evaluate("Number(document.querySelector('.w.active')?.id.slice(2) ?? -1)")
        words = json.load(open(f"{DATA}/{PARK}.timing.json"))["words"]
        if act < 0 or words[act]["sentence"] != 6: return f"?s=6 landed in sentence {words[act]['sentence'] if act >= 0 else None}"
        pg.evaluate("document.querySelector('audio').pause()")
        go("#/insights"); go("#/library"); pg.go_back(); pg.wait_for_timeout(500)
        return "#/insights" in pg.url or pg.url
    step("deep link ?s=6&play=1 starts at that sentence; browser Back works", deeplinks)

    # ---- insights reacts to a rating
    def insights_rating():
        before = api(BASE, "ratings/summary")["data"]
        t = api(BASE, "ratings/trial")["data"]
        api(BASE, "ratings", {"trialId": t["trialId"], "aToken": t["a"]["token"], "bToken": t["b"]["token"], "preferred": "a", "ratingA": 4, "ratingB": 2, "raterId": "5b0d1c2e-7a3f-4c11-9d2e-1a2b3c4d5e6f"})
        after = api(BASE, "ratings/summary")["data"]
        return json.dumps(after) != json.dumps(before) or "summary did not change after a rating"
    step("a submitted rating changes the ratings summary", insights_rating)

    # ---- offline / API down
    def api_down():
        pg2 = ctx.new_page(); pg2.route("**/api/**", lambda r: r.abort())
        pg2.goto(BASE + "#/assignments"); pg2.wait_for_timeout(1500)
        t = pg2.inner_text("main"); shown = re.search(r"could not|try again|couldn.t", t, re.I) is not None and not re.search(r"/api/|ECONN|Failed to fetch|TypeError", t)
        pg2.unroute("**/api/**"); retry = pg2.get_by_role("button", name="Try again")
        if retry.count(): retry.click(); pg2.wait_for_timeout(1200)
        ok = pg2.locator("main").inner_text() != t; pg2.close()
        return (shown and ok) or f"friendly error={shown}, recovered={ok}: {t[:120]}"
    step("API down: friendly error without internals, Try again recovers", api_down)
    step("audio file missing: reader still shows the text", lambda: (lambda p2: (p2.route("**/*.mp3", lambda r: r.abort()), p2.goto(BASE + f"#/read/{PARK}"), p2.wait_for_selector(".w"), p2.wait_for_timeout(1500), p2.locator("button[aria-label=Play]").click(), p2.wait_for_timeout(1200), (p2.locator(".w").count() > 100 and "audio could not be loaded" in p2.inner_text("main")), p2.close())[-2])(ctx.new_page()) or "no message when audio fails")

    # ---- generation scenarios (slow)
    def busy():
        long = " ".join(["The quick brown fox jumps over the lazy dog near the old river bank."] * 12)
        a = api(BASE, "generate", {"title": "Busy one", "text": long, "language": "en"})
        try:
            api(BASE, "generate", {"title": "Busy two", "text": long, "language": "en"}); second = 200
        except urllib.error.HTTPError as e: second = e.code
        go("#/generate"); pg.fill("#g-title", "Busy three"); pg.fill("#g-text", long); pg.get_by_role("button", name="Create passage").click(); pg.wait_for_timeout(1200)
        t = pg.inner_text("main")
        for _ in range(120):
            j = api(BASE, "jobs/" + a["data"]["jobId"])["data"]
            if j["status"] in ("done", "failed"): break
            time.sleep(2)
        return (second == 429 and re.search(r"another passage|try again in a moment|busy", t, re.I) is not None) or f"second={second}, ui={t[-200:]}"
    step("generator busy: API says 429, the screen says so in plain words", busy)
    def xss():
        title = "<img src=x onerror=window.__x=1>Safe title"; text = "The robot said <b>hello</b> to the children. <script>window.__x=2</script> They waved back and smiled all day long."
        go("#/generate"); pg.fill("#g-title", title); pg.fill("#g-text", text); pg.get_by_role("button", name="Create passage").click()
        for _ in range(100):
            pg.wait_for_timeout(1500)
            if pg.get_by_role("button", name="Start another").count(): break
        go("#/library"); pg.wait_for_selector(".pcard"); pg.wait_for_timeout(500)
        flag = pg.evaluate("window.__x"); lib_txt = pg.inner_text("main")
        card = pg.locator(".pcard", has_text="Safe title").first; card.get_by_role("link", name=re.compile("^Read")).click(); pg.wait_for_selector(".w"); pg.wait_for_timeout(600)
        return (flag is None and pg.evaluate("window.__x") is None and "<img" not in pg.inner_text("main") and "<img" not in lib_txt and "Safe title" in lib_txt) or f"script ran={flag} / library text: '{lib_txt[:200]}'"
    step("hostile title and text are shown as plain text and never run", xss)
    def recording_variant():
        src = f"{DATA}/{DAY}.mp3"; tj = json.load(open(f"{DATA}/{DAY}.timing.json")); text = " ".join(w["text"] for w in tj["words"])
        go("#/generate"); pg.fill("#g-title", "Recording variant test"); pg.fill("#g-text", text); pg.set_input_files("#g-rec", src); pg.wait_for_timeout(300)
        pg.get_by_role("button", name="Create passage").click()
        for _ in range(160):
            pg.wait_for_timeout(1500)
            if pg.get_by_role("button", name="Start another").count(): break
        else: return "did not finish"
        go("#/library"); pg.wait_for_selector(".pcard"); pg.locator(".pcard", has_text="Recording variant test").first.get_by_role("link", name=re.compile("^Read")).click(); pg.wait_for_selector(".w"); pg.wait_for_timeout(800)
        a = pg.get_by_role("button", name="Human narration"); c = pg.get_by_role("button", name="Read-aloud voice")
        if a.count() != 1 or c.count() != 1: return "voice choice buttons missing"
        (a if not a.is_disabled() else c).click(); pg.wait_for_timeout(1500)
        pg.locator("button[aria-label=Play]").click(); pg.wait_for_timeout(1500)
        return pg.evaluate("document.querySelector('audio').currentTime") > 0.5 or "recording variant does not play"
    step("teacher recording: uploaded, aligned, both voices selectable and playable", recording_variant)
    def regenerate():
        go("#/review"); pg.wait_for_timeout(1000)
        b = pg.get_by_role("button", name="Regenerate with current fixes")
        if not b.count(): return True  # nothing to review in this data
        listed = lambda: {p["id"] for p in api(BASE, "passages")["data"]}
        before = listed()
        b.first.click(); pg.wait_for_timeout(1500)
        for _ in range(120):
            pg.wait_for_timeout(2000)
            vanished = before - listed()
            if vanished: return f"a passage disappeared from the Library while it was regenerated: {sorted(vanished)[0][:8]}"
            if pg.get_by_role("button", name="Regenerate with current fixes").first.is_enabled(): break
        if before - listed(): return "a passage is missing from the Library after regeneration"
        return pg.get_by_role("button", name="Regenerate with current fixes").first.is_enabled() or "regeneration did not finish"
    step("words to check: Regenerate runs a job, finishes, and the passage stays in the Library throughout", regenerate)

    errs = sorted(set(p for p in problems))
    results.append(not errs); print(("PASS " if not errs else "FAIL ") + "no uncaught page errors" + ("" if not errs else f" — {errs[:5]}"))
    b.close()
print(f"{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
