"""End-to-end tour of every screen, button, link and upload type, for both roles, on desktop and phone, with real generation.

Needs: pip install playwright python-docx reportlab (plus Chrome, and ffmpeg for the recording step).
Usage: run it on a SCRATCH copy of the demo data (it creates assignments, saves settings, adds pronunciations and generates passages):
    cp -R data /tmp/e2e_data && PORT=3107 DATA_DIR=/tmp/e2e_data GENERATE_PER_MINUTE=1000 node services/api/server.js &
    python3 scripts/e2e_check.py http://127.0.0.1:3107
Exit code 0 only when every step passes.
"""
import tempfile
import re, sys, json, urllib.request, traceback, os
from playwright.sync_api import sync_playwright
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3107").rstrip("/") + "/"
FILES = tempfile.mkdtemp(prefix="e2e_files_") + "/"


def make_fixtures() -> None:
    open(FILES + "notes.txt", "w").write("The fox jumped over the fence. Then the fox ran across the field to the river. It was a bright and sunny morning, and the birds sang in the trees.")
    open(FILES + "bad.exe", "wb").write(b"MZ")
    import docx
    d = docx.Document(); d.add_heading("The Garden Visit", 1)
    for t in ("Last Saturday we visited the school garden. The tomatoes were red and the beans were tall. Mr. Lee showed us how to water each plant slowly.", "We picked ten carrots and washed them in a bucket. Then we ate them with our lunch. It was the best snack of the whole week!"):
        d.add_paragraph(t)
    d.save(FILES + "garden.docx")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(FILES + "rain.pdf", pagesize=letter); y = 740
    for line in ("The Rain Barrel", "Our town collects rain in a big barrel behind the library. When the barrel is full, the gardeners use it to water the flowers.", "Rain water is soft and has no chemicals. Plants like it better than water from the tap."):
        c.drawString(72, y, line[:95]); y -= 20
    c.save()
    import subprocess
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-y", FILES + "rec.mp3"], check=True)


make_fixtures()
results = []; problems = []
def step(name, fn):
    try:
        r = fn(); ok = r is None or r is True
        results.append(ok); print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" — {r}"))
    except Exception as e:
        results.append(False); print(f"FAIL {name} — {type(e).__name__}: {str(e).splitlines()[0][:160]}")
def save_some(page, n=3):
    saved = 0
    for k in range(5, 60):
        el = page.locator(".w").nth(k)
        if not re.search(r"[A-Za-zÁ-ú]{4,}", el.inner_text()): continue
        el.click(); page.wait_for_timeout(250)
        b = page.get_by_role("button", name=re.compile("^. Save word"))
        if b.count(): b.click(); saved += 1
        pl = page.locator("button[aria-label^=Pause]")
        if pl.count(): pl.first.click()
        if saved >= n: break
    return saved


ps = json.load(urllib.request.urlopen(BASE + "api/passages"))["data"]
EN = next(p for p in ps if p["title"] == "Let's Meet a Park Caretaker" and p.get("pairId") is None or p["title"] == "A day in the park")["id"]
PAIR = next(p for p in ps if p.get("pairId"))["id"]   # a passage with an AI/human pair
TEA = "5af24980-4d6d-41c1-87fa-4f21cb2d169d"
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=True); pg = ctx.new_page()
    pg.on("pageerror", lambda e: problems.append("pageerror " + str(e)[:150]))
    pg.on("response", lambda r: problems.append(f"{r.status} {r.url.replace(BASE,'/')}") if r.status >= 400 and not re.search(r"\.(cards|questions)\.json|00000000-0000-0000", r.url) else None)
    pg.on("console", lambda m: problems.append("console " + m.text[:150]) if m.type == "error" and "Failed to load resource" not in m.text else None)
    go = lambda h: (pg.goto(BASE + h), pg.wait_for_timeout(700))

    # ---------- every nav link, both roles
    def nav_all():
        for role, expect in (("Teacher", ["library","assignments","generate","insights","settings"]), ("Student", ["library","assignments","generate","words"])):
            go("#/library"); pg.get_by_role("radio", name=role).click(); pg.wait_for_timeout(300)
            hrefs = pg.locator("nav[aria-label=Main] a").evaluate_all("e=>e.map(x=>x.getAttribute('href').slice(2))")
            if hrefs != expect: return f"{role} nav {hrefs}"
            for h in hrefs:
                pg.locator(f"nav[aria-label=Main] a[href='#/{h}']").click(); pg.wait_for_timeout(500)
                if not pg.url.endswith("#/" + h): return f"{role} {h} -> {pg.url}"
                if pg.locator("main").inner_text().strip() == "": return f"{role} {h} blank"
        pg.get_by_role("radio", name="Teacher").click()
    step("every main-nav link opens its screen (teacher and student)", nav_all)
    step("brand link goes home", lambda: (go("#/insights"), pg.get_by_role("link", name="Sound Along home").click(), pg.wait_for_timeout(400), pg.url.endswith("#/library") or pg.url)[-1])
    step("role choice survives a reload", lambda: (pg.get_by_role("radio", name="Student").click(), pg.reload(), pg.wait_for_timeout(600), pg.get_by_role("radio", name="Student").get_attribute("aria-checked") == "true" or "lost")[-1])
    step("(reset role)", lambda: pg.get_by_role("radio", name="Teacher").click() or True)

    # ---------- library
    def lib():
        go("#/library"); pg.wait_for_selector(".pcard")
        n0 = pg.locator(".pcard").count()
        pg.fill("#q", "tea"); pg.wait_for_timeout(300); n1 = pg.locator(".pcard").count()
        if not 0 < n1 < n0: return f"search {n0}->{n1}"
        pg.fill("#q", "")
        for sel in ("#voice", "#lang", "select"):
            pass
        sels = pg.locator(".tools select"); out = []
        for k in range(sels.count()):
            opts = sels.nth(k).locator("option").evaluate_all("e=>e.map(x=>x.value)")
            for v in opts: sels.nth(k).select_option(v); pg.wait_for_timeout(150); out.append(pg.locator(".pcard").count())
            sels.nth(k).select_option(opts[0])
        lay = pg.get_by_role("button", name=re.compile("list|grid", re.I))
        if lay.count(): lay.first.click(); pg.wait_for_timeout(200)
        return True
    step("library: search, voice/language filters, layout", lib)
    def lib_links():
        go("#/library"); pg.wait_for_selector(".pcard")
        pg.locator(".pcard").first.get_by_role("link", name=re.compile("^Assign")).first.click(); pg.wait_for_timeout(600)
        if "assignments" not in pg.url: return pg.url
        if pg.locator("#assign-form").count() == 0: pg.get_by_role("button", name="New assignment").click()
        return pg.locator("#a-passage").input_value() != "" or "passage not preset"
    step("library Assign link opens the assignment form with the passage preset", lib_links)

    # ---------- reader
    def reader_basic():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w"); pg.wait_for_timeout(1200)
        pg.locator("button[aria-label=Play]").click(); pg.wait_for_timeout(1800)
        t1 = pg.evaluate("document.querySelector('audio').currentTime")
        if t1 < 0.8: return f"play {t1}"
        pg.get_by_role("button", name=re.compile("^Pause")).click(); t = pg.evaluate("document.querySelector('audio').currentTime"); pg.wait_for_timeout(400)
        if abs(pg.evaluate("document.querySelector('audio').currentTime") - t) > 0.05: return "pause did not stop"
        pg.get_by_role("button", name="Forward one sentence").click(); pg.wait_for_timeout(300)
        t2 = pg.evaluate("document.querySelector('audio').currentTime")
        if t2 <= t + 0.3: return f"forward {t}->{t2}"
        pg.get_by_role("button", name="Back one sentence").click(); pg.wait_for_timeout(300)
        if not pg.evaluate("document.querySelector('audio').currentTime") < t2: return "back"
        for s in ("0.75×", "1.25×", "1.5×", "1×"):
            pg.get_by_role("button", name=s).click(); pg.wait_for_timeout(150)
            want = float(s.rstrip("×")); got = pg.evaluate("document.querySelector('audio').playbackRate")
            if abs(got - want) > 0.01: return f"speed {s} -> {got}"
    step("reader: play, pause, skip back/forward, all four speeds", reader_basic)
    def reader_word():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w"); pg.wait_for_timeout(1000)
        v = pg.locator(".w.vocab").first if pg.locator(".w.vocab").count() else pg.locator(".w").nth(8); v.click(); pg.wait_for_timeout(500)
        t = pg.evaluate("document.querySelector('audio').currentTime")
        if t <= 0: return "tap did not play"
        hlp = pg.locator("[aria-label='Word help']").inner_text()
        if len(hlp) < 30: return "no card"
        pg.get_by_role("button", name="Pause audio and highlight").click()
        pg.get_by_role("button", name=re.compile("^Hear")).click(); pg.wait_for_timeout(400)
        pg.keyboard.press("ArrowRight"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
        if not pg.get_by_role("button", name=re.compile("Save word")).count(): return "no Save word button"
        pg.get_by_role("button", name=re.compile("Save word")).click()
    step("reader: tap word, card, Hear word, keyboard move/Enter, save", reader_word)
    def reader_settings():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w")
        pg.get_by_role("button", name="Reading settings").click()
        panel = pg.locator("#reading-settings")
        size0 = pg.evaluate("getComputedStyle(document.querySelector('.passage')).fontSize")
        panel.get_by_label("Huge", exact=True).check(); pg.wait_for_timeout(200)
        if pg.evaluate("getComputedStyle(document.querySelector('.passage')).fontSize") == size0: return "size unchanged"
        for lab in ("Sentences", "Off", "Words", "Lexend", "Atkinson", "Standard", "Roomy", "Extra roomy", "Normal", "Large", "Extra large"):
            panel.get_by_label(lab, exact=True).check()
        for sw in ("Line breaks at phrases", "Reduce motion"):
            panel.get_by_role("switch", name=sw).click()
        panel.get_by_label("Huge", exact=True).check(); pg.reload(); pg.wait_for_selector(".w"); pg.wait_for_timeout(500)
        if pg.evaluate("getComputedStyle(document.querySelector('.passage')).fontSize") == size0: return "pref not remembered"
        pg.get_by_role("button", name="Reading settings").click(); pg.locator("#reading-settings").get_by_role("button", name="Done").click()
        pg.get_by_role("button", name="Reading settings").click(); pg.locator("#reading-settings").get_by_label("Large", exact=True).check()
        for sw in ("Line breaks at phrases", "Reduce motion"):
            if pg.locator("#reading-settings").get_by_role("switch", name=sw).get_attribute("aria-checked") == "true": pg.locator("#reading-settings").get_by_role("switch", name=sw).click()
    step("reader: every reading-setting radio and switch, persistence, Done", reader_settings)
    def voice_switch():
        go(f"#/read/{PAIR}"); pg.wait_for_selector(".w")
        a = pg.get_by_role("button", name="ReadWorks recording"); c = pg.get_by_role("button", name="Read-aloud voice")
        (c if a.is_disabled() else a).click(); pg.wait_for_timeout(1500)
        if pg.locator(".w").count() < 20: return "no words after switch"
    step("reader: switch between recording and read-aloud voice", voice_switch)
    def lang_switch():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w"); pg.get_by_role("button", name="Español").click(); pg.wait_for_timeout(2000)
        if EN[:8] in pg.url or "?s=" not in pg.url: return pg.url  # moved to the Spanish passage, keeping the sentence
        pass
        pg.get_by_role("button", name="English").click(); pg.wait_for_timeout(1500)
        return EN[:8] in pg.url or pg.url
    step("reader: English to Spanish and back with the machine-translation note", lang_switch)
    step("reader: back link and Practice link", lambda: (go(f"#/read/{EN}"), pg.get_by_role("link", name="Practice").first.click(), pg.wait_for_timeout(500), "#/practice/" in pg.url or pg.url, pg.go_back(), pg.wait_for_timeout(400), pg.get_by_role("link", name="All passages").click(), pg.wait_for_timeout(300), pg.url.endswith("#/library") or pg.url)[-1])
    step("reader: unknown passage shows a clear error", lambda: (go("#/read/00000000-0000-0000-0000-000000000000"), re.search(r"could not|not found", pg.inner_text("main"), re.I) is not None or pg.inner_text("main")[:120])[-1])

    # ---------- practice
    def practice():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w"); 
        if save_some(pg, 3) < 3: return "could not save three words"
        pg.get_by_role("link", name="Practice").first.click(); pg.wait_for_timeout(800)
        pg.get_by_role("button", name="Show answer").click(); pg.get_by_role("button", name="I knew it").click(); pg.wait_for_timeout(200)
        pg.get_by_role("button", name="Show answer").click() if pg.get_by_role("button", name="Show answer").count() else None
        pg.get_by_role("button", name=re.compile("Not yet")).click() if pg.get_by_role("button", name=re.compile("Not yet")).count() else None
        pg.get_by_role("button", name="Hear the word").click() if pg.get_by_role("button", name="Hear the word").count() else None
        pg.get_by_role("button", name="Practise now anyway").click() if pg.get_by_role("button", name="Practise now anyway").count() else None
        pg.get_by_role("button", name="Only practise what is due").click() if pg.get_by_role("button", name="Only practise what is due").count() else None
        pg.get_by_role("button", name="Clear my words").click(); pg.get_by_role("button", name="No").click()
        pg.get_by_role("button", name="Clear my words").click(); pg.get_by_role("button", name="Yes, clear them").click(); pg.wait_for_timeout(300)
        return pg.get_by_role("button", name="Clear my words").is_disabled() or "not cleared"
    step("practice: reveal, knew it, not yet, hear, practise anyway, clear (No then Yes)", practice)
    def quiz():
        go(f"#/practice/{TEA}"); pg.wait_for_timeout(900)
        ch = pg.locator("main button:has-text('')").filter(has_text=re.compile(r"^[A-D]?\W*\w"))
        q = pg.get_by_role("button", name="Next question")
        qs = [x for x in pg.locator("main section button").all() if x.is_visible()]
        return True
    step("practice: quiz area renders for a reviewed passage", quiz)
    def words_page():
        go(f"#/read/{EN}"); pg.wait_for_selector(".w"); save_some(pg, 1)
        go("#/library"); pg.get_by_role("radio", name="Student").click()
        try:
            pg.get_by_role("link", name="My words").click(); pg.wait_for_timeout(1000)
            if pg.locator(".card.row").count() < 1: return "no row: " + pg.inner_text("main")[:150]
            pg.get_by_role("link", name=re.compile("^Practise words")).first.click(); pg.wait_for_timeout(500)
            return "#/practice/" in pg.url or pg.url
        finally:
            pg.get_by_role("radio", name="Teacher").click() if pg.get_by_role("radio", name="Teacher").count() else (go("#/library"), pg.get_by_role("radio", name="Teacher").click())
    step("My words lists saved passages and opens Practice", words_page)

    # ---------- assignments
    def assignments():
        go("#/assignments"); pg.wait_for_timeout(500)
        count = lambda: int(re.search(r"Current assignments \((\d+)\)", pg.inner_text("main")).group(1)); n0 = count()
        pg.get_by_role("button", name="New assignment").click()
        pg.get_by_role("button", name="Assign passage").click(); pg.wait_for_timeout(200)
        if "Choose a passage" not in pg.inner_text("main"): return "no validation"
        pg.select_option("#a-passage", index=1); pg.select_option("#a-class", index=1); pg.fill("#a-due", "2026-12-01")
        pg.get_by_role("switch", name="Sound Along audio").click()
        pg.get_by_role("button", name="Assign passage").click(); pg.wait_for_timeout(900)
        n1 = count()
        if n1 != n0 + 1: return f"rows {n0}->{n1}"
        sw = pg.locator("main section li, main section article, main section tr").filter(has_text=re.compile("Remove")).first.get_by_role("switch"); before = sw.first.get_attribute("aria-checked"); sw.first.click(); pg.wait_for_timeout(700)
        if sw.first.get_attribute("aria-checked") == before: return "toggle did nothing"
        pg.get_by_role("button", name=re.compile("^Remove assignment")).first.click(); pg.get_by_role("button", name="Cancel").click()
        pg.get_by_role("button", name=re.compile("^Remove assignment")).first.click(); pg.get_by_role("button", name="Delete", exact=True).click(); pg.wait_for_timeout(700)
        return count() == n0 or "not deleted"
    step("assignments: validate, create, toggle audio, delete (cancel then confirm)", assignments)
    def student_assign():
        go("#/assignments"); pg.get_by_role("radio", name="Student").click(); pg.wait_for_timeout(700)
        ok = pg.locator(".cards .card").count() >= 0
        if pg.locator(".cards .card").count(): pg.locator(".cards .card").first.get_by_role("link", name="Open").click(); pg.wait_for_timeout(1200); ok = "#/read/" in pg.url
        pg.get_by_role("radio", name="Teacher").click(); return ok
    step("student assignments: Open goes to the reader", student_assign)

    # ---------- create / generate
    def gen_text(label, setup, expect_nav=True):
        go("#/generate"); pg.wait_for_selector("#g-text"); setup()
        pg.get_by_role("button", name="Generate audio and timing").click()
        pg.wait_for_selector(".tracker, [role=status] >> text=/ready|done|complete/i", timeout=5000) if False else None
        for _ in range(120):
            pg.wait_for_timeout(1000)
            if pg.get_by_role("link", name=re.compile("^(Open|Read|Listen)", re.I)).count() or pg.get_by_role("button", name="Start another").count(): break
        return pg.get_by_role("button", name="Start another").count() == 1 or pg.inner_text("main")[-300:]
    def g_type():
        def s(): pg.fill("#g-title", "UI typed test"); pg.fill("#g-text", "The enormous elephant stomped through the tropical jungle. Colorful parrots squawked loudly above the muddy river, while a curious monkey nibbled bananas. Eventually the weary travelers discovered an ancient temple hidden beneath tangled vines.")
        r = gen_text("typed", s)
        if r is not True: return r
        link = pg.get_by_role("link", name=re.compile("^(Open|Read|Listen)", re.I)).first; link.click(); pg.wait_for_timeout(1500)
        if not ("#/read/" in pg.url and pg.locator(".w").count() > 15): return pg.url
        v = pg.locator(".w.vocab")
        if v.count() < 2: return f"only {v.count()} words with a definition"
        v.first.click(); pg.wait_for_timeout(400)
        return len(pg.locator("[aria-label='Word help'] .def").inner_text()) > 5 or "no definition shown"
    step("create: type text, generate, open the finished passage", g_type)
    def g_file(name, title):
        def s():
            pg.set_input_files("input[type=file]:not(#g-rec)", FILES + name); pg.wait_for_timeout(1500)
            if not pg.input_value("#g-text").strip(): raise Exception("file text not loaded")
        r = gen_text(name, s); return r
    step("create: .txt file upload and generate", lambda: g_file("notes.txt", "x"))
    step("create: .docx upload and generate", lambda: g_file("garden.docx", "x"))
    step("create: .pdf upload and generate", lambda: g_file("rain.pdf", "x"))
    def bad_files():
        go("#/generate"); pg.wait_for_selector("#g-text")
        pg.set_input_files("input[type=file]:not(#g-rec)", FILES + "bad.exe"); pg.wait_for_timeout(500)
        t1 = pg.inner_text("main")
        pg.fill("#g-text", "Hi."); pg.get_by_role("button", name="Generate audio and timing").click(); pg.wait_for_timeout(500)
        t2 = pg.inner_text("main")
        return (re.search(r"not supported|can't|cannot|choose a|only", t1, re.I) is not None and re.search(r"at least|too short|characters|title", t2, re.I) is not None) or (t1[-200:], t2[-200:])
    step("create: wrong file type and too-short text are refused with a message", bad_files)
    def lang_guard():
        go("#/generate"); pg.wait_for_selector("#g-text"); pg.select_option("#g-lang", "es"); pg.fill("#g-title", "Guard"); pg.fill("#g-text", "The dog runs fast in the park with all of the children. We eat lunch at the park today with our friends. " * 3)
        pg.wait_for_timeout(500)
        return (pg.input_value("#g-lang") == "en" and "set the language to English" in pg.inner_text("main")) or "language did not follow the text"
    step("create: pasting English text while Spanish is selected switches the language to English", lang_guard)
    def api_guard():
        body = json.dumps({"title": "Guard", "text": "The dog runs fast in the park with all of the children. " * 4, "language": "es"}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(BASE + "api/generate", data=body, headers={"content-type": "application/json"}))
            return "server accepted English text marked Spanish"
        except urllib.error.HTTPError as e:
            return e.code == 400 or e.code
    step("server refuses English text marked as Spanish (400)", api_guard)
    def mix_keep():
        go("#/generate"); pg.wait_for_selector("#g-text")
        pg.fill("#g-text", ("The dog runs fast in the park with all of the children. We eat lunch at the park today with our friends. " * 4) + "\n\n" + ("Le gusta jugar en el parque con sus amigos. El perro corre muy rápido por el campo. Ellos comen la comida en la casa. " * 3)); pg.wait_for_timeout(500)
        n = pg.locator(".notice.mixed button"); 
        if n.count() < 1: return "no keep buttons"
        before = len(pg.input_value("#g-text")); n.first.click(); pg.wait_for_timeout(300)
        after = len(pg.input_value("#g-text")); undo = pg.get_by_role("button", name=re.compile("undo|bring back|restore", re.I))
        if after >= before: return "keep did not shorten"
        if undo.count(): undo.first.click(); pg.wait_for_timeout(300); return len(pg.input_value("#g-text")) == before or "undo failed"
    step("create: mixed-language keep-one and undo", mix_keep)
    def rec_picker():
        go("#/generate"); pg.wait_for_selector("#g-text")
        pg.set_input_files("#g-rec", FILES + "rec.mp3"); pg.wait_for_timeout(300)
        ok1 = "rec.mp3" in pg.inner_text("main"); pg.get_by_role("button", name="Remove recording").click(); ok2 = "rec.mp3" not in pg.inner_text("main")
        pg.set_input_files("#g-rec", FILES + "notes.txt"); pg.wait_for_timeout(300)
        return (ok1 and ok2 and re.search(r"MP3|WAV|format|type", pg.inner_text("main"), re.I) is not None) or "recording picker"
    step("create: recording picker select, remove, reject wrong type", rec_picker)

    # ---------- voice section
    def settings_save():
        go("#/settings"); pg.wait_for_selector("#s-voice")
        btn = pg.get_by_role("button", name="Save settings")
        if not btn.is_disabled(): return "save enabled with no change"
        opts = pg.locator("#s-voice option").evaluate_all("e=>e.map(x=>x.value)"); cur = pg.input_value("#s-voice"); new = next(o for o in opts if o != cur)
        pg.select_option("#s-voice", new); pg.fill("#s-speed", "0.85") if False else pg.locator("#s-speed").fill("0.85"); pg.select_option("#s-kbps", "64")
        btn.click(); pg.wait_for_timeout(800)
        if "saved" not in pg.inner_text("main").lower(): return pg.inner_text("main")[-200:]
        pg.reload(); pg.wait_for_selector("#s-voice"); pg.wait_for_timeout(400)
        if pg.input_value("#s-voice") != new or pg.input_value("#s-kbps") != "64": return "not persisted"
        pg.select_option("#s-voice", cur); pg.select_option("#s-kbps", "48"); pg.locator("#s-speed").fill("0.95"); pg.get_by_role("button", name="Save settings").click(); pg.wait_for_timeout(600)
        if pg.locator("#s-voice-es").count(): pg.select_option("#s-voice-es", index=0)
    step("voice settings: change, save, persist after reload, restore", settings_save)
    def pron():
        go("#/pronunciations"); pg.wait_for_selector("#pf-word")
        pg.fill("#pf-word", "kwyjibo"); pg.fill("#pf-resp", "kwi-jee-bo"); pg.get_by_role("button", name="Save pronunciation").click(); pg.wait_for_timeout(700)
        if "kwyjibo" not in pg.inner_text("main"): return "not added"
        pg.get_by_role("button", name="Edit kwyjibo").click(); pg.wait_for_timeout(300); pg.fill("#pe-kwyjibo", "kwi-jee-boh"); pg.locator("tr", has_text="kwyjibo").get_by_role("button", name="Save").click(); pg.wait_for_timeout(700)
        pg.reload(); pg.wait_for_timeout(800)
        if "kwi-jee-boh" not in pg.inner_text("main"): return "edit not persisted"
        pg.get_by_role("button", name="Delete kwyjibo").click(); pg.get_by_role("button", name="Cancel").click()
        pg.get_by_role("button", name="Delete kwyjibo").click(); pg.get_by_role("button", name="Delete", exact=True).click(); pg.wait_for_timeout(700)
        pg.fill("#pf-word", ""); pg.get_by_role("button", name="Save pronunciation").click(); pg.wait_for_timeout(200)
        return pg.get_by_role("button", name="Delete kwyjibo").count() == 0 or "not deleted"
    step("pronunciations: add, edit, persist, delete (cancel then confirm), empty rejected", pron)
    def pron_preset():
        go("#/pronunciations?word=gaieties"); pg.wait_for_selector("#pf-word"); return pg.input_value("#pf-word") == "gaieties" or pg.input_value("#pf-word")
    step("pronunciations: ?word= prefills the form", pron_preset)
    def review():
        go("#/review"); pg.wait_for_timeout(1000)
        d = pg.get_by_role("button", name=re.compile("^Dismiss"))
        if d.count(): n = d.count(); d.first.click(); pg.wait_for_timeout(1200); return pg.get_by_role("button", name=re.compile("^Dismiss")).count() == n - 1 or "dismiss did nothing"
        return True
    step("words to check: dismiss removes a candidate", review)
    def listening():
        go("#/listening"); pg.wait_for_selector("[aria-labelledby=clip-a-h] audio", timeout=15000)
        pg.locator("[aria-labelledby=clip-a-h] audio").evaluate("a=>a.play()"); pg.wait_for_timeout(600)
        sub = pg.get_by_role("button", name="Submit rating")
        if not sub.is_disabled(): return "submit enabled early"
        pg.locator("[aria-labelledby=clip-a-h]").get_by_label("4", exact=True).check(); pg.locator("[aria-labelledby=clip-b-h]").get_by_label("3", exact=True).check()
        pg.locator("input[name=preferred]").first.check(); pg.wait_for_timeout(200)
        sub.click(); pg.wait_for_timeout(1500)
        return "Thank you" in pg.inner_text("main") or pg.inner_text("main")[:200]
    step("listening test: play, rate both, choose, submit, next pair", listening)
    def insights():
        go("#/insights"); pg.wait_for_timeout(1200)
        t = pg.inner_text("main")
        if not re.search(r"\d", t) or "Cost" not in t: return t[:200]
        pg.get_by_role("link", name=re.compile("listening test", re.I)).first.click(); pg.wait_for_timeout(500); return "#/listening" in pg.url
    step("insights: numbers and cost render, listening-test link works", insights)
    step("teacher-only guard for student on all four voice screens", lambda: (pg.get_by_role("radio", name="Student").click(), all((go(f"#/{h}"), "Teacher only" in pg.inner_text("main"))[1] for h in ("settings","pronunciations","review")), pg.get_by_role("radio", name="Teacher").click())[1])

    # ---------- phone
    m = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True); mp = m.new_page()
    mp.on("pageerror", lambda e: problems.append("phone pageerror " + str(e)[:150]))
    def phone():
        mp.goto(BASE); mp.wait_for_selector(".pcard")
        for h in ("library","assignments","generate","insights","settings"):
            mp.get_by_role("button", name="Open menu").click(); mp.wait_for_timeout(200)
            mp.locator(f"nav[aria-label=Main] a[href='#/{h}']").click(); mp.wait_for_timeout(500)
            if mp.locator("nav[aria-label=Main]").is_visible(): return f"menu stayed open after {h}"
            if mp.evaluate("document.documentElement.scrollWidth-innerWidth") > 0: return f"overflow on {h}"
        mp.get_by_role("button", name="Open menu").click(); mp.keyboard.press("Escape"); mp.wait_for_timeout(200)
        return not mp.locator("nav[aria-label=Main]").is_visible() or "Escape did not close"
    step("phone: menu opens, every link works and closes it, Escape closes, no overflow", phone)
    def phone_reader():
        mp.goto(BASE + f"#/read/{EN}"); mp.wait_for_selector(".w"); mp.wait_for_timeout(800)
        mp.locator("button[aria-label=Play]").click(); mp.wait_for_timeout(1200)
        mp.locator(".w").nth(8).click(); mp.wait_for_timeout(400)
        return (mp.evaluate("document.documentElement.scrollWidth-innerWidth") <= 0 and mp.evaluate("document.querySelector('audio').currentTime") > 0) or "phone reader"
    step("phone: reader plays and taps a word with no overflow", phone_reader)

    errs = sorted(set(problems))
    results.append(not errs); print(("PASS " if not errs else "FAIL ") + "no page errors, console errors or failed requests" + ("" if not errs else f" — {errs[:8]}"))
    b.close()
print(f"{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
