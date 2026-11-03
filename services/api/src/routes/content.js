import { HttpError, ok, route } from "../http.js";
import { parseRespelling, parseWord } from "../pronunciations.js";
import { buildReviewItems } from "../review.js";
import { effectiveSettings, mergeSettings, parseSettingsPatch } from "../settings.js";

const limited = (limiter) => (req, res, next) =>
  limiter(req.ip) ? next() : next(new HttpError(429, "Too many changes in a short time. Wait a minute and try again."));

/** Settings, pronunciation fixes and the pronunciation review queue. */
export function contentRoutes(api, { store, catalog, voices, writeLimiter }) {
  const writes = limited(writeLimiter);
  const viewOf = (settings) => ({ ...effectiveSettings(settings), voices });

  api.get("/settings", route(async (req, res) => res.json(ok(viewOf(await store.getSettings())))));

  api.put(
    "/settings",
    writes,
    route(async (req, res) => {
      const patch = parseSettingsPatch(req.body, voices);
      const saved = await store.putSettings(mergeSettings(await store.getSettings(), patch));
      res.json(ok(viewOf(saved)));
    }),
  );

  api.get("/pronunciations", route(async (req, res) => res.json(ok(await store.listPronunciations()))));

  api.put(
    "/pronunciations/:word",
    writes,
    route(async (req, res) => {
      const word = parseWord(req.params.word);
      const { pronunciation, created } = await store.putPronunciation(word, parseRespelling(req.body));
      res.status(created ? 201 : 200).json(ok(pronunciation));
    }),
  );

  api.delete(
    "/pronunciations/:word",
    writes,
    route(async (req, res) => {
      const word = parseWord(req.params.word);
      if (!(await store.deletePronunciation(word))) throw new HttpError(404, "That pronunciation fix no longer exists.");
      res.json(ok({ word }));
    }),
  );

  api.get(
    "/review",
    route(async (req, res) => {
      const [sources, dismissed, fixes] = await Promise.all([
        catalog.reviewSources?.() ?? [],
        store.listDismissed(),
        store.listPronunciations(),
      ]);
      res.json(ok(buildReviewItems({ sources, dismissed, fixed: fixes.map((p) => p.word) })));
    }),
  );

  api.post(
    "/review/dismiss",
    writes,
    route(async (req, res) => {
      const word = parseWord(req.body?.word);
      await store.addDismissed(word);
      res.json(ok({ word }));
    }),
  );
}
