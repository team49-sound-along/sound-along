import { HttpError, ok, route } from "../http.js";
import { classSettingsView, effectiveClassSettings, parseClassSettingsPatch } from "../readAloud/classSettings.js";
import { readAloudInsights, readerInsights } from "../readAloud/insightsService.js";
import { READER_CODE, parseReadAloudResult } from "../readAloud/parse.js";

const limited = (limiter) => (req, res, next) =>
  limiter(req.ip) ? next() : next(new HttpError(429, "Too many changes in a short time. Wait a minute and try again."));

/**
 * Anonymous read-aloud results and the teacher's view of them.
 *   POST /read-aloud/results         one result at the end of a session (counts and word positions only)
 *   GET|PUT /read-aloud/settings     the teacher's switches (per class, and the default)
 *   GET /insights/read-aloud         org / class / passage view
 *   GET /insights/read-aloud/readers per-reader view (404 unless the class has "progress by reader" on)
 */
export function readAloudRoutes(api, { store, catalog, readyList, passageIds, classIds, writeLimiter }) {
  const writes = limited(writeLimiter);
  const timingOf = (id) => catalog.timing?.(id) ?? null;
  const viewOf = async () => classSettingsView(await store.getClassSettings(), await store.listClasses());

  api.get("/read-aloud/settings", route(async (req, res) => res.json(ok(await viewOf()))));

  api.put(
    "/read-aloud/settings",
    writes,
    route(async (req, res) => {
      const { key, patch } = parseClassSettingsPatch(req.body, await classIds());
      await store.putClassSettings(key, patch);
      res.json(ok(await viewOf()));
    }),
  );

  api.post(
    "/read-aloud/results",
    writes,
    route(async (req, res) => {
      const passages = await passageIds();
      const id = typeof req.body?.passageId === "string" ? req.body.passageId : "";
      const result = parseReadAloudResult(req.body, { passageIds: passages, classIds: await classIds(), timing: passages.has(id) ? await timingOf(id) : null });
      const settings = effectiveClassSettings(await store.getClassSettings(), result.classId);
      if (!settings.share) return res.json(ok({ recorded: false })); // sharing is off for this class: nothing is kept
      await store.recordReadAloud({ ...result, readerCode: settings.readers ? result.readerCode : null }); // a code is kept only when the class switch is on
      return res.json(ok({ recorded: true }));
    }),
  );

  const filtersOf = async (query) => {
    const passageId = query.passageId ? String(query.passageId) : null;
    const classId = query.classId ? String(query.classId) : null;
    if (passageId && !(await passageIds()).has(passageId)) throw new HttpError(400, "Unknown passage.");
    if (classId && !(await classIds()).has(classId)) throw new HttpError(400, "Unknown class.");
    return { passageId, classId };
  };

  api.get(
    "/insights/read-aloud",
    route(async (req, res) => {
      const filters = await filtersOf(req.query);
      const [passages, classes] = await Promise.all([readyList(), store.listClasses()]);
      res.json(ok(await readAloudInsights({ store, timingOf, passages: passages.map((p) => ({ id: p.id, title: p.title })), classes, filters })));
    }),
  );

  api.get(
    "/insights/read-aloud/readers",
    route(async (req, res) => {
      const { passageId, classId } = await filtersOf(req.query);
      const code = req.query.code ? String(req.query.code) : null;
      if (!classId) throw new HttpError(400, "Choose a class.");
      if (code && !READER_CODE.test(code)) throw new HttpError(400, "That reader code is not valid.");
      const view = await readerInsights({ store, timingOf, classId, code, passageId });
      if (!view) throw new HttpError(404, "Progress by reader is off for this class.");
      res.json(ok(view));
    }),
  );
}
