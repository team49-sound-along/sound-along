import { HttpError, ok, route } from "../http.js";
import { classSettingsView, effectiveClassSettings, parseClassSettingsPatch } from "../readAloud/classSettings.js";
import { readAloudInsights, readerInsights } from "../readAloud/insightsService.js";
import { READER_CODE, parseReadAloudResult } from "../readAloud/parse.js";

const limited = (limiter) => (req, res, next) =>
  limiter(req.ip) ? next() : next(new HttpError(429, "Too many changes in a short time. Wait a minute and try again."));

/**
 * READER_INSIGHTS flag: reader codes need teacher sign-in before they are safe to collect, so the flag is OFF in the deployed stack.
 *
 * ACCESS: POST /read-aloud/results is anonymous by design and strictly validated. The teacher routes (PUT settings, the two insights GETs)
 * have exactly the protection of the other teacher routes (settings, pronunciations, assignments, questions): the write rate limit on writes,
 * the same limiter family on reads, and on AWS the same CloudFront-signed origin. There is NO sign-in or teacher-to-class check on the API in
 * this build; the teacher screens are guarded in the app only. Real authentication (for example Cognito and a verified token, with the
 * teacher's classes checked on every call) is required before production, and matters most for the reader-code endpoint. Defence in depth that
 * needs no sign-in: reader data is empty unless the class switch is on and the class has enough sessions, unknown classes and passages are
 * refused, lists and result sizes are capped, and all reads are bounded queries.
 *
 * Anonymous read-aloud results and the teacher's view of them.
 *   POST /read-aloud/results         one result at the end of a session (counts and word positions only)
 *   GET|PUT /read-aloud/settings     the teacher's switches (per class, and the default)
 *   GET /insights/read-aloud         org / class / passage view
 *   GET /insights/read-aloud/readers per-reader view (an empty view unless the class has "progress by reader" on)
 */
export function readAloudRoutes(api, { store, catalog, readyList, passageIds, classIds, writeLimiter, readLimiter, readerInsightsOn = false }) {
  const writes = limited(writeLimiter);
  const reads = (req, res, next) => (readLimiter(req.ip) ? next() : next(new HttpError(429, "Too many requests. Wait a minute and try again.")));
  const timingOf = (id) => catalog.timing?.(id) ?? null;
  // READER_INSIGHTS (server flag, off in the deployed stack until teacher sign-in exists): when off, reader codes are neither stored nor shown,
  // the readers route is a 404, and the settings never report "progress by reader" as on, so devices send no code.
  const withFlag = (view) => ({
    ...view,
    readersAvailable: readerInsightsOn,
    defaults: { ...view.defaults, readers: readerInsightsOn && view.defaults.readers },
    classes: view.classes.map((c) => ({ ...c, readers: readerInsightsOn && c.readers })),
  });
  const viewOf = async () => withFlag(classSettingsView(await store.getClassSettings(), await store.listClasses()));

  api.get("/read-aloud/settings", reads, route(async (req, res) => res.json(ok(await viewOf()))));

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
      await store.recordReadAloud({ ...result, readerCode: readerInsightsOn && settings.readers ? result.readerCode : null }); // a code is kept only when the class switch is on
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
    reads,
    route(async (req, res) => {
      const filters = await filtersOf(req.query);
      const [passages, classes] = await Promise.all([readyList(), store.listClasses()]);
      res.json(ok(await readAloudInsights({ store, timingOf, passages: passages.map((p) => ({ id: p.id, title: p.title })), classes, filters, readersEnabled: readerInsightsOn })));
    }),
  );

  api.get(
    "/insights/read-aloud/readers",
    reads,
    route(async (req, res) => {
      const { passageId, classId } = await filtersOf(req.query);
      const code = req.query.code ? String(req.query.code) : null;
      if (!readerInsightsOn) throw new HttpError(404, "Unknown API route.");
      if (!classId) throw new HttpError(400, "Choose a class.");
      if (code && !READER_CODE.test(code)) throw new HttpError(400, "That reader code is not valid.");
      res.json(ok(await readerInsights({ store, timingOf, classId, code, passageId })));
    }),
  );
}
