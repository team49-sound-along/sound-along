"""A long upload through the real Create page: ONE passage per language, a progress bar with the time left, nothing listed until it is all ready, no parts anywhere.

Usage (on a SCRATCH copy of data/, the upload takes a few minutes): python3 scripts/e2e_long.py <server url> [text file]
Without a text file it uses a generated text of about 1,300 words.
"""
import json
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
SENTENCES = ["The children walked to the lake before sunrise.", "A cold wind moved across the water and the reeds bent low.",
             "Nobody spoke, because the morning was too beautiful for words.", "Then a heron rose from the shore and flew toward the hills."]


def text():
    if len(sys.argv) > 2:
        return open(sys.argv[2], encoding="utf-8").read()
    paragraphs = [" ".join(SENTENCES[(i + k) % 4] + f" Number {i * 7 + k}." for k in range(8)) for i in range(26)]
    return "A Morning at the Lake\n\n" + "\n\n".join(paragraphs)


def api(path):
    return json.load(urllib.request.urlopen(BASE + "api/" + path))["data"]


results, problems = [], []


def step(name, ok, detail=""):
    results.append(ok is True)
    print(("PASS " if ok is True else "FAIL ") + name + (f": {detail}" if detail and ok is not True else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    pg = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    pg.on("pageerror", lambda e: problems.append(str(e)[:120]))
    base = {p["id"] for p in api("passages")}
    pg.goto(BASE + "#/generate"); pg.wait_for_selector("#g-title")
    pg.fill("#g-title", "A Morning at the Lake"); pg.fill("#g-text", text())
    notice = pg.inner_text("main")
    step("a long text says it takes a few minutes and is one passage (no parts)", "few minutes" in notice and not re.search(r"\bparts?\b", notice, re.I), notice[-200:])
    pg.get_by_role("button", name="Create passage").click()
    started, seen, first_listing, saw_part, percent = time.time(), [], None, False, 0
    while time.time() - started < 1500:
        pg.wait_for_timeout(3000)
        body = pg.inner_text("main")
        m = re.search(r"(\d+)% done(?: · ([^\n]+))?", body)
        if m and (not seen or seen[-1] != m.group(0)):
            seen.append(m.group(0))
        saw_part = saw_part or bool(re.search(r"\bParts?\b|\d+ parts", body))
        percent = int(m.group(1)) if m else percent
        now = [p for p in api("passages") if p["id"] not in base]
        if now and first_listing is None:
            first_listing = (len(now), percent)  # how many passages, and how far along the progress bar was, the first time anything was listed
        if "Open in reader" in body or "Open with" in body:
            break
    step("a progress bar with a percentage and the time left appears while it works", len(seen) >= 2 and any("left" in x for x in seen), str(seen))
    step("the page never says part", not saw_part)
    # The passages are listed a moment before the page notices the job is done, so the rule is: never one language without the other, never before the end.
    step("nothing is listed until the work is finished, and then both languages appear together", first_listing == (2, 99) or first_listing == (2, 100), str(first_listing))
    time.sleep(3)
    new = [p for p in api("passages") if p["id"] not in base]
    step("one English and one Spanish passage appear together, neither a part of a document", len(new) == 2 and {p["language"] for p in new} == {"en", "es"} and not any(p.get("series") for p in new), str([(p["title"], p["language"]) for p in new]))
    step("both titles are the plain title, with no part numbers", all(not re.search(r"\((?:Part|Parte) \d", p["title"]) for p in new), str([p["title"] for p in new]))
    pg.goto(BASE + "#/library"); pg.reload(); pg.wait_for_timeout(1500)
    step("the Library shows no parts", not re.search(r"\bParts?\b| parts\b", pg.inner_text("main")))
    english = next((p for p in new if p["language"] == "en"), None)
    if english:
        t = json.load(urllib.request.urlopen(BASE + f"data/{english['id']}.timing.json"))
        w = t["words"]
        step("word times keep increasing across the whole passage", all(w[k]["start_ms"] <= w[k + 1]["start_ms"] for k in range(len(w) - 1)))
        pg.goto(BASE + f"#/read/{english['id']}"); pg.wait_for_selector(".w"); pg.wait_for_timeout(800)
        pg.locator("button[aria-label=Play]").click(); pg.wait_for_timeout(1200)
        pg.locator(".w").nth(len(w) - 4).click(); pg.wait_for_timeout(800)
        got = pg.evaluate("document.querySelector('audio').currentTime")
        step("tapping a word at the very end plays that word (one audio, one timeline)", abs(got - w[len(w) - 4]["start_ms"] / 1000) < 1.5, f"{got}s vs {w[len(w) - 4]['start_ms'] / 1000}s")
        step("the reader never mentions parts", not re.search(r"\bParts?\b|Next part", pg.inner_text("main")))
    step("no page errors", not problems, str(problems))
    browser.close()
print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
