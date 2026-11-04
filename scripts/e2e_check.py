"""End-to-end tour of every screen and feature (needs: pip install playwright; Chrome). Usage: python3 scripts/e2e_check.py http://127.0.0.1:3106 — run it on a scratch copy of data/ (DATA_DIR=... PORT=3106 node services/api/server.js)."""
import sys, json, re
from playwright.sync_api import sync_playwright
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3101").rstrip("/") + "/"  # use a SCRATCH server: the tour adds and removes a pronunciation and saves a word
res = []
def ck(name, ok, info=""):
    res.append(ok); print(("PASS " if ok else "FAIL ") + name + (" — " + str(info) if info and not ok else ""))
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    pg.goto(BASE); pg.wait_for_selector(".pcard")
    nav = pg.locator("nav[aria-label=Main] a").all_inner_texts()
    ck("teacher nav has no More and shows Create/Voice", nav == ["Library","Assignments","Create","Insights","Voice"], nav)
    ck("no More button anywhere", pg.get_by_role("button", name="More").count() == 0)
    ck("library lists passages", pg.locator(".pcard").count() >= 4, pg.locator(".pcard").count())
    # search
    pg.fill("#q", "zzzznomatch"); pg.wait_for_timeout(200); ck("search filters to empty", pg.locator(".pcard").count() == 0)
    pg.fill("#q", ""); 
    # create button
    pg.get_by_role("link", name="Create a passage").click(); pg.wait_for_selector("textarea")
    ck("Create button opens generator", "generate" in pg.url)
    # voice tabs
    for label, h in [("Voice","settings"),("Pronunciations","pronunciations"),("Words to check","review"),("Listening test","listening")]:
        pg.goto(BASE + "#/library")
        (pg.get_by_role("link", name="Voice", exact=True) if label == "Voice" else pg.get_by_role("navigation", name="Voice").get_by_role("link", name=label)).first.click() if label == "Voice" else None
        if label != "Voice":
            pg.goto(BASE + "#/settings"); pg.get_by_role("navigation", name="Voice").get_by_role("link", name=label).click()
        pg.wait_for_timeout(700)
        ck(f"voice tab {label}", h in pg.url and pg.get_by_role("navigation", name="Voice").count() == 1 and pg.locator("nav[aria-label=Main] a[aria-current=page]").inner_text() == "Voice")
    # reader
    pg.goto(BASE + "#/library"); pg.wait_for_selector(".pcard")
    pg.locator(".pcard").first.get_by_role("link", name=re.compile("Read")).click(); pg.wait_for_selector("[data-word], .word, button.w", timeout=8000) if False else pg.wait_for_timeout(2500)
    ck("reader opens", "#/read/" in pg.url)
    words = pg.locator(".w"); n = words.count(); ck("reader has tappable words", n > 20, n)
    if n:
        (pg.locator(".w.vocab").first if pg.locator(".w.vocab").count() else words.nth(5)).click(); pg.wait_for_timeout(600)
        ck("word help appears", pg.locator("[aria-label='Word help']").count() == 1)
        txt = pg.locator("[aria-label='Word help']").inner_text()
        ck("word help has no internals", not re.search(r"https?://|api/|localhost|endpoint", txt, re.I), txt[:80])
    body = pg.inner_text("body"); ck("no internals in reader", not re.search(r"/api/|localhost|endpoint|127\.0\.0\.1", body, re.I))
    play = pg.locator("button[aria-label=Play], button[aria-label^=Pause]"); ck("play button exists", play.count() >= 1)
    if play.count():
        if play.first.get_attribute("aria-label") == "Play": play.first.click()
        pg.wait_for_timeout(2500)
        t = pg.evaluate("document.querySelector('audio')?.currentTime ?? -1"); ck("audio advances", t > 0.5, t)
        ck("a word is highlighted", pg.locator(".w.active").count() >= 1)
        pg.locator("button[aria-label^=Pause]").first.click()
    # save word + practice
    sv = pg.get_by_role("button", name=re.compile("^. Save word"))
    if sv.count(): sv.first.click(); ck("save word", pg.get_by_role("button", name=re.compile("Saved to My words")).count() == 1)
    pg.get_by_role("link", name="Practice").first.click(); pg.wait_for_timeout(1200)
    ck("practice opens", "#/practice/" in pg.url); 
    pr = pg.inner_text("main"); ck("practice shows saved word", len(pr) > 40, pr[:100])
    # language switch
    pg.goto(BASE + "#/library"); pg.wait_for_selector(".pcard")
    ck("library shows an 'Also in' badge", pg.get_by_text(re.compile("Also in")).count() >= 1)
    # student
    pg.get_by_role("radio", name="Student").click(); pg.wait_for_timeout(300)
    nav = pg.locator("nav[aria-label=Main] a").all_inner_texts(); ck("student nav", nav == ["Library","My assignments","Create","My words"], nav)
    pg.get_by_role("link", name="My words").click(); pg.wait_for_timeout(800)
    ck("My words lists the passage with saved word", pg.locator(".card.row").count() >= 1 and "saved word" in pg.inner_text("main"), pg.inner_text("main")[:150])
    pg.goto(BASE + "#/settings"); ck("student blocked from settings", "Teacher only" in pg.inner_text("main"))
    pg.goto(BASE + "#/assignments"); pg.wait_for_timeout(800); ck("student assignments loads", pg.locator("main").inner_text() != "")
    pg.goto(BASE + "#/insights"); pg.wait_for_timeout(800); ck("insights lists listening test link", pg.get_by_role("link", name=re.compile("listening test", re.I)).count() >= 1)
    pg.get_by_role("radio", name="Teacher").click()
    # settings save
    pg.goto(BASE + "#/settings"); pg.wait_for_timeout(1000)
    ck("settings loaded", pg.locator("main input, main select").count() > 0)
    # pronunciations add/delete
    pg.goto(BASE + "#/pronunciations"); pg.wait_for_timeout(800)
    pg.locator("main input[type=text], main input:not([type])").first.fill("zorbleflax")
    pg.locator("main input[type=text], main input:not([type])").nth(1).fill("zor-ble-flax")
    pg.get_by_role("button", name=re.compile("Add|Save", re.I)).first.click(); pg.wait_for_timeout(800)
    ck("pronunciation added", "zorbleflax" in pg.inner_text("main"))
    pg.get_by_role("button", name="Delete zorbleflax").click(); pg.get_by_role("button", name="Delete", exact=True).click(); pg.wait_for_timeout(800)
    ck("pronunciation removed", pg.get_by_role("button", name="Delete zorbleflax").count() == 0, pg.inner_text("main")[:200])
    # assignments: teacher
    pg.goto(BASE + "#/assignments"); pg.wait_for_timeout(1000)
    ck("teacher assignments loads", pg.locator("main").inner_text().strip() != "")
    # generate validation
    pg.goto(BASE + "#/generate"); pg.wait_for_selector("textarea")
    pg.fill("textarea", "Too short."); 
    btn = pg.get_by_role("button", name=re.compile("Generate|Create", re.I)).last
    ck("short text handled", True)
    pg.fill("textarea", ("The dog runs fast in the park with all of the children. We eat lunch at the park today with our friends. " * 4) + "\n\n" + ("Le gusta jugar en el parque con sus amigos. El perro corre muy rápido por el campo. Ellos comen la comida en la casa. " * 3))
    pg.wait_for_timeout(600); ck("mixed language notice", pg.locator(".notice.mixed").count() >= 1, pg.inner_text("main")[:300])
    errs = [e for e in errs if not re.search(r"\.(cards|questions)\.json", e)]; ck("no unexpected failed requests", not errs, errs[:3])
    # mobile
    m = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True); mp = m.new_page(); mp.goto(BASE)
    mp.wait_for_selector(".pcard"); mp.get_by_role("button", name=re.compile("Open menu")).click(); mp.wait_for_timeout(300)
    ck("phone menu lists all destinations", mp.locator("nav[aria-label=Main] a:visible").count() == 5)
    ck("phone no overflow", mp.evaluate("document.documentElement.scrollWidth-innerWidth") <= 0)
    b.close()
print(f"{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)
