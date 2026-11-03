import path from "node:path";
import { HttpError, fail, ok, route } from "../http.js";
import { buildTrial, parseRating } from "../ratings/trial.js";
import { summarizeRatings } from "../ratings/summary.js";

const AB_FILE = /^[0-9a-f]{16}\.mp3$/;
const PAUSED = "Listening ratings are paused right now. Please try again later.";

/** Blind listening test: GET trial, POST rating, GET summary. `manifest.read()` -> clips[]. */
export function ratingRoutes(api, { store, manifest, writeLimiter, config, random = Math.random }) {
  const clips = async () => (manifest ? manifest.read() : []);

  api.get("/ratings/trial", route(async (req, res) => res.json(ok(buildTrial(await clips(), random)))));

  api.post(
    "/ratings",
    route(async (req, res) => {
      if (!config.generationEnabled) throw new HttpError(503, PAUSED);
      const rating = parseRating(req.body, await clips());
      if (!writeLimiter(req.ip)) throw new HttpError(429, "Too many ratings in a short time. Wait a minute and try again.");
      await store.addRating({ ...rating, createdAt: new Date().toISOString() });
      res.json(ok({ recorded: true }));
    }),
  );

  api.get("/ratings/summary", route(async (req, res) => res.json(ok(summarizeRatings(await store.listRatings())))));
}

/** Local clip route. Strict 16-hex token file names only, so the manifest (and anything else in ab/) is never served. */
export function mountLocalClips(app, { config }) {
  app.get("/data/ab/:file", (req, res) => {
    if (!config.dataDir || !AB_FILE.test(req.params.file)) return res.status(404).json(fail("File not found."));
    return res.sendFile(path.join(config.dataDir, "ab", req.params.file), { dotfiles: "deny", maxAge: 0 }, (err) => {
      if (err && !res.headersSent) res.status(404).json(fail("File not found."));
    });
  });
}
