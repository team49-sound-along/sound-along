import { HttpError, ok, route } from "../http.js";
import { UUID } from "../recordings/rules.js";
import { buildApprovedDocument, cleanDraft, parsePublishInput, summarizeDraft } from "../questions/draft.js";

const UNAVAILABLE = "Reviewing questions is not available right now.";
const NO_DRAFT = "There is no question draft for that passage.";

/**
 * Teacher review of generated practice questions.
 *   GET  /questions/drafts            passages that have a draft (a summary each)
 *   GET  /questions/drafts/:id        one draft, every question pending
 *   POST /questions/drafts/:id/publish  writes the served file with ONLY the approved questions
 * A draft is never served to students: only publish writes the document they read. `questions` is { listDraftIds, readDraft, publish }.
 * Like the other teacher routes there is no sign-in on the API; the teacher screen is guarded in the app only.
 */
export function questionRoutes(api, { questions, readyList, writeLimiter, now = () => new Date() }) {
  const store = () => {
    if (!questions) throw new HttpError(503, UNAVAILABLE);
    return questions;
  };
  const idOf = (req) => {
    if (!UUID.test(req.params.id)) throw new HttpError(404, NO_DRAFT);
    return req.params.id;
  };
  async function loadDraft(id) {
    const view = cleanDraft(await store().readDraft(id), id);
    if (!view) throw new HttpError(404, NO_DRAFT);
    return view;
  }

  api.get(
    "/questions/drafts",
    route(async (req, res) => {
      const [ids, passages] = await Promise.all([store().listDraftIds(), readyList()]);
      const ready = new Map(passages.map((p) => [p.id, p]));
      const views = await Promise.all(ids.filter((id) => ready.has(id)).map(async (id) => cleanDraft(await questions.readDraft(id), id)));
      const list = views
        .filter((view) => view && view.questions.length > 0)
        .map((view) => ({ ...summarizeDraft(view), language: ready.get(view.passageId).language ?? "en" }))
        .sort((a, b) => a.title.localeCompare(b.title));
      res.json(ok(list));
    }),
  );

  api.get(
    "/questions/drafts/:id",
    route(async (req, res) => res.json(ok(await loadDraft(idOf(req))))),
  );

  api.post(
    "/questions/drafts/:id/publish",
    (req, res, next) => (writeLimiter(req.ip) ? next() : next(new HttpError(429, "Too many changes in a short time. Wait a minute and try again."))),
    route(async (req, res) => {
      const id = idOf(req);
      const view = await loadDraft(id);
      const approved = parsePublishInput(req.body, view);
      if (!(await readyList()).some((p) => p.id === id)) throw new HttpError(404, "That passage is not in the library.");
      const doc = buildApprovedDocument(view, approved, now());
      await questions.publish(id, doc);
      res.json(ok({ passageId: id, published: doc.questions.length, reviewedAt: doc.reviewedAt }));
    }),
  );
}
