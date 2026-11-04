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
 * Protection is exactly that of the other teacher writes (settings, pronunciations, assignments, generate): the same write rate limit and,
 * on AWS, the same CloudFront-signed origin. There is NO sign-in or teacher check on the API in this build; the teacher screen is guarded
 * in the app only. Real authentication (for example Cognito and a verified token) is required before production, for all teacher routes.
 */
export const MAX_DRAFTS_PER_LIST = 200;

export function questionRoutes(api, { questions, readyList, writeLimiter, now = () => new Date(), logger = console }) {
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
      const candidates = ids.filter((id) => ready.has(id)).sort();
      const batch = candidates.slice(0, MAX_DRAFTS_PER_LIST);
      // one unreadable draft must not take the whole list down: skip it and log the passage id (never the contents)
      const views = await Promise.all(
        batch.map(async (id) => {
          try {
            return cleanDraft(await questions.readDraft(id), id);
          } catch (err) {
            logger.error("question draft unreadable, skipped", { passageId: id, message: err?.message });
            return null;
          }
        }),
      );
      const list = views
        .filter((view) => view && view.questions.length > 0)
        .map((view) => ({ ...summarizeDraft(view), language: ready.get(view.passageId).language ?? "en" }))
        .sort((a, b) => a.title.localeCompare(b.title));
      res.json(ok(list, { more: candidates.length > batch.length, limit: MAX_DRAFTS_PER_LIST, total: candidates.length }));
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
