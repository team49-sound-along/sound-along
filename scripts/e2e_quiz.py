"""End-to-end check of the question review and quiz flow: a teacher approves two questions and publishes, a student takes the quiz.

Run it on a SCRATCH copy of the demo data (it publishes a questions file):
    cp -R data /tmp/e2e_data && rm -f /tmp/e2e_data/*.questions.json
    DATA_DIR=/tmp/e2e_data node services/api/scripts/seedQuestionDrafts.js --from samples/questions-v2
    PORT=3117 DATA_DIR=/tmp/e2e_data node services/api/server.js &
    AXE_JS=/path/to/axe.min.js python3 scripts/e2e_quiz.py http://127.0.0.1:3117
Exit code 0 only when every step passes. AXE_JS is optional (the accessibility checks are skipped without it).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3117").rstrip("/") + "/"
PARK = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
AXE = open(os.environ["AXE_JS"]).read() if os.environ.get("AXE_JS") else None
results: list[bool] = []


def step(name, fn):
    try:
        r = fn()
        ok = r is None or r is True
        results.append(ok)
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" - {r}"))
    except Exception as e:  # noqa: BLE001
        results.append(False)
        print(f"FAIL {name} - {type(e).__name__}: {str(e).splitlines()[0][:200]}")


def _status(url):
    try:
        return urllib.request.urlopen(url).status
    except urllib.error.HTTPError as e:
        return e.code


def axe(page, label):
    if not AXE:
        return True
    page.evaluate(AXE)
    found = page.evaluate("async () => (await axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21aa']})).violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).join(' | '))")
    return True if not found else f"{label}: {found}"


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 1100, "height": 900})
    page = ctx.new_page()
    page.goto(BASE + "#/library")
    page.wait_for_timeout(600)

    # ---- before anything is published
    step("no questions file yet and no Quiz button", lambda: (page.goto(BASE + f"#/read/{PARK}"), page.wait_for_timeout(800), page.get_by_role("link", name="Quiz", exact=True).count() == 0 or "button shown")[-1])
    step("a draft is not reachable by students", lambda: all(_status(BASE + p) == 404 for p in (f"data/{PARK}.draft.json", f"data/question-drafts/{PARK}.draft.json", f"data/{PARK}.questions.json")) or "reachable")

    # ---- teacher
    page.goto(BASE + "#/questions")
    page.get_by_role("radio", name="Teacher").click()
    page.wait_for_timeout(600)
    step("teacher sees the three drafts, all unpublished", lambda: (page.locator("li.card.item").count() == 3 and page.get_by_text("Not published").count() == 3) or page.locator("main").inner_text()[:300])
    step("student cannot open the review screen", lambda: (page.get_by_role("radio", name="Student").click(), page.wait_for_timeout(300), page.get_by_role("heading", name="Teacher only").count() == 1 or "not guarded", page.get_by_role("radio", name="Teacher").click(), page.wait_for_timeout(300))[2])
    step("review list accessibility", lambda: axe(page, "list"))
    page.get_by_role("link", name=re.compile("^Review .*Caretaker")).click()
    page.wait_for_timeout(800)
    cards = page.locator("ol.cards > li")
    step("every question starts undecided; publish is disabled", lambda: (cards.count() >= 3 and page.get_by_text("Not decided", exact=True).count() == cards.count() and page.get_by_role("button", name="Publish approved questions").is_disabled()) or "state wrong")
    step("evidence sentence, correct answer and automatic checks are shown", lambda: (cards.first.get_by_text("Correct answer").count() == 1 and cards.first.locator("blockquote").count() == 1 and cards.first.locator(".checks li").count() >= 1) or "missing")
    step("no review label from a person or an AI is shown", lambda: not re.search(r"reviewed by|\bAI\b", page.locator("main").inner_text()) or "found a review label")
    step("review screen accessibility", lambda: axe(page, "review"))
    cards.nth(0).get_by_role("button", name="Approve").click()
    cards.nth(1).get_by_role("button", name="Reject").click()
    cards.nth(2).get_by_role("button", name="Approve").click()
    step("edit text works and is kept", lambda: (cards.nth(2).get_by_role("button", name="Edit text").click(), cards.nth(2).get_by_label("Question", exact=True).fill("Edited question for the test?"), cards.nth(2).get_by_role("button", name="Save text").click(), page.wait_for_timeout(200), cards.nth(2).get_by_text("Edited question for the test?").count() == 1 or "edit lost")[-1])
    step("an invalid edit is refused with a message", lambda: (cards.nth(2).get_by_role("button", name="Edit text").click(), cards.nth(2).get_by_label("Question", exact=True).fill(""), cards.nth(2).get_by_role("button", name="Save text").click(), cards.nth(2).get_by_role("alert").count() == 1 or "no message", cards.nth(2).get_by_role("button", name="Cancel").click())[2])
    step("choices survive a reload", lambda: (page.reload(), page.wait_for_timeout(900), page.locator(".top .badge", has_text="Approved").count() == 2 and page.locator(".top .badge", has_text="Rejected").count() == 1 or "lost")[-1])
    step("publish becomes available and publishes", lambda: (page.get_by_role("button", name="Publish approved questions").click(), page.wait_for_selector("text=Published 2 questions"), True)[-1])
    served = json.load(urllib.request.urlopen(BASE + f"data/{PARK}.questions.json"))
    step("the served file has only the two approved questions", lambda: (served["reviewed"] is True and len(served["questions"]) == 2 and any(q["question"] == "Edited question for the test?" for q in served["questions"]) and "review" not in json.dumps(served).replace("reviewed", "")) or served)

    # ---- student
    page.goto(BASE + "#/library")
    page.get_by_role("radio", name="Student").click()
    page.goto(BASE + f"#/read/{PARK}")
    page.wait_for_timeout(900)
    step("student sees the Quiz button on that passage", lambda: page.get_by_role("link", name="Quiz", exact=True).count() == 1 or "missing")
    page.get_by_role("link", name="Quiz", exact=True).click()
    page.wait_for_timeout(700)
    step("quiz shows Question 1 of 2 and a progress bar", lambda: (page.get_by_text("Question 1 of 2").count() == 1 and page.locator("progress").count() == 1) or "wrong")
    step("quiz accessibility (question)", lambda: axe(page, "quiz"))
    radios = page.locator("button.choice")
    step("keyboard: Tab reaches a choice and Enter answers", lambda: (radios.count() >= 2, [page.keyboard.press("Tab") for _ in range(8) if not page.evaluate("document.activeElement.classList.contains('choice')")], page.keyboard.press("Enter"), page.wait_for_timeout(300), page.locator(".feedback .verdict").count() == 1 or "no answer by keyboard")[-1])
    step("feedback sits in a live region and the Next button has focus", lambda: (page.locator(".feedback[aria-live=polite]").count() == 1 and page.evaluate("document.activeElement.textContent.includes('Next question')")) or "no live region or focus")
    step("Show me where is offered after an answer", lambda: page.get_by_role("link", name="Show me where").count() == 1 or "missing")
    step("feedback accessibility", lambda: axe(page, "feedback"))
    href = page.get_by_role("link", name="Show me where").get_attribute("href")
    page.get_by_role("link", name="Show me where").click()
    page.wait_for_timeout(1500)
    step("Show me where opens the reader at that sentence", lambda: (re.search(rf"#/read/{PARK}\?s=\d+$", page.url) is not None and page.locator(".w.band").count() > 0) or f"{page.url} band={page.locator('.w.band').count()}")
    def evidence_on_screen():
        page.wait_for_timeout(2500)  # pictures above the sentence load after the first paint and must not push it off screen
        top = page.evaluate("(() => { const w = document.querySelector('.w.active'); const r = w && w.getBoundingClientRect(); return r ? [r.top, innerHeight] : null })()")
        return (top is not None and 0 <= top[0] < top[1] - 120) or f"the sentence is not on screen: {top}"
    step("the sentence is on screen after the pictures have loaded", evidence_on_screen)
    page.go_back()
    page.wait_for_timeout(800)
    step("Back returns to the same question with the answer kept", lambda: (page.get_by_text("Question 1 of 2").count() == 1 and page.locator(".feedback .verdict").count() == 1) or "progress lost")
    page.get_by_role("button", name="Next question").click()
    page.locator("button.choice").nth(1).click()
    page.get_by_role("button", name="See my score").click()
    page.wait_for_timeout(300)
    step("final score screen with a per-question review", lambda: (re.search(r"Your score: \d of 2", page.locator("main").inner_text()) is not None and page.locator("ol.review > li").count() == 2) or page.locator("main").inner_text()[:200])
    step("score screen accessibility", lambda: axe(page, "score"))
    step("the score is saved on this device only", lambda: (page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('soundalong.quiz.v1.')).length") == 1) or "not saved")
    step("Retry starts again at question 1", lambda: (page.get_by_role("button", name="Retry").click(), page.wait_for_timeout(300), page.get_by_text("Question 1 of 2").count() == 1 or "no restart")[-1])

    # ---- phone width and reduced motion
    phone = browser.new_context(viewport={"width": 360, "height": 740}, reduced_motion="reduce")
    p2 = phone.new_page()
    p2.goto(BASE + f"#/quiz/{PARK}")
    p2.wait_for_timeout(800)
    step("phone: no horizontal scroll on the quiz", lambda: p2.evaluate("document.documentElement.scrollWidth <= window.innerWidth") or "overflow")
    step("phone: quiz accessibility", lambda: axe(p2, "phone quiz"))
    p2.goto(BASE + "#/questions/" + PARK)
    p2.get_by_role("radio", name="Teacher").click()
    p2.wait_for_timeout(900)
    step("phone: no horizontal scroll on the review screen", lambda: p2.evaluate("document.documentElement.scrollWidth <= window.innerWidth") or "overflow")
    browser.close()

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
