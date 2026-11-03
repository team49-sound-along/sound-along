import express from "express";
import path from "node:path";
import { HttpError, errorHandler, fail, ok, route } from "./http.js";
import { buildInsights } from "./insights.js";
import { createRateLimiter } from "./rateLimit.js";
import { contentRoutes } from "./routes/content.js";
import { mountLocalClips, ratingRoutes } from "./routes/ratings.js";
import { createFileManifest } from "./ratings/manifest.js";
import { summarizeRatings } from "./ratings/summary.js";
import { generationRoutes } from "./routes/generation.js";
import { mountLocalRecordingUpload, recordingRoutes } from "./routes/recordings.js";
import { loadVoices } from "./settings.js";
import { parseAssignmentInput, parseEvent, parseToggle } from "./validate.js";

const DATA_FILE = /^[0-9a-f-]{36}\.(mp3|timing\.json|soundalong\.json)$/;

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Content-Security-Policy":
    "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; media-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
};

/**
 * Build the Express app from injected dependencies so every part is testable and swappable:
 *   store    assignments + events      (file store locally, DynamoDB on AWS)
 *   catalog  passages + timings        (data folder locally, S3 on AWS)
 *   jobs     job registry (async)      (memory locally, DynamoDB on AWS)
 *   runner   starts generation         (child process locally, Step Functions on AWS)
 *   recordings  human recording slots   (local disk, or S3 presigned PUT)
 *   manifest blind-test clip manifest   (<dataDir>/ab/manifest.json locally, S3 data/ab/manifest.json on AWS)
 *   sources  stored job input by id     (raw/<id>.json on disk or S3; used by regenerate)
 */
export function createApp({ store, catalog, jobs, runner, recordings, sources, config, manifest = config.dataDir ? createFileManifest(config.dataDir) : null, random, logger = console }) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", config.trustProxy ?? false);
  app.use((req, res, next) => {
    res.set(SECURITY_HEADERS);
    next();
  });
  const generateLimiter = createRateLimiter({ max: config.generatePerMinute, windowMs: 60_000 });
  const writeLimiter = createRateLimiter({ max: config.writePerMinute ?? 60, windowMs: 60_000 });

  // The raw audio upload streams its own body, so it is mounted before the JSON parser.
  mountLocalRecordingUpload(app, { recordings, config, writeLimiter });
  app.use(express.json({ limit: "64kb" }));

  const passageIds = async () => new Set((await catalog.list()).map((p) => p.id));
  const classIds = async () => new Set((await store.listClasses()).map((c) => c.id));

  const api = express.Router();

  api.get("/health", (req, res) => {
    res.json(ok({ status: "ok", generation: { enabled: config.generationEnabled } }));
  });

  api.get("/passages", route(async (req, res) => res.json(ok(await catalog.list()))));
  api.get("/classes", route(async (req, res) => res.json(ok(await store.listClasses()))));
  api.get("/assignments", route(async (req, res) => res.json(ok(await store.listAssignments()))));

  api.post(
    "/assignments",
    route(async (req, res) => {
      const [passages, classes] = await Promise.all([catalog.list(), store.listClasses()]);
      const input = parseAssignmentInput(req.body, {
        passageIds: new Set(passages.map((p) => p.id)),
        classIds: new Set(classes.map((c) => c.id)),
      });
      const created = await store.createAssignment({
        ...input,
        passageTitle: passages.find((p) => p.id === input.passageId).title,
        className: classes.find((c) => c.id === input.classId).name,
      });
      res.status(201).json(ok(created));
    }),
  );

  api.patch(
    "/assignments/:id",
    route(async (req, res) => {
      const updated = await store.updateAssignment(req.params.id, parseToggle(req.body));
      if (!updated) throw new HttpError(404, "That assignment no longer exists.");
      res.json(ok(updated));
    }),
  );

  api.delete(
    "/assignments/:id",
    route(async (req, res) => {
      if (!(await store.deleteAssignment(req.params.id))) throw new HttpError(404, "That assignment no longer exists.");
      res.json(ok({ id: req.params.id }));
    }),
  );

  generationRoutes(api, { store, jobs, runner, recordings, sources, config, generateLimiter });
  recordingRoutes(api, { recordings, config, writeLimiter });
  ratingRoutes(api, { store, manifest, writeLimiter, config, random });
  contentRoutes(api, { store, catalog, voices: config.voices ?? loadVoices(), writeLimiter });

  api.get(
    "/jobs/:id",
    route(async (req, res) => {
      const job = await jobs.get(req.params.id);
      if (!job) return res.status(404).json(fail("That job was not found."));
      return res.json(ok({ humanPassageId: null, ...job }));
    }),
  );

  api.post(
    "/events",
    route(async (req, res) => {
      const event = parseEvent(req.body, await passageIds());
      await store.recordEvent(event.type);
      res.json(ok({ recorded: true }));
    }),
  );

  api.get(
    "/insights",
    route(async (req, res) => {
      const [timings, assignments, events, qualityReport, ratings] = await Promise.all([
        catalog.timings(),
        store.listAssignments(),
        store.eventCounts(),
        catalog.qualityReport?.() ?? null,
        store.listRatings?.() ?? [],
      ]);
      const blindRating = ratings.length > 0 ? summarizeRatings(ratings) : null;
      res.json(ok(buildInsights({ timings, assignments, events, qualityReport, blindRating })));
    }),
  );

  api.use((req, res) => res.status(404).json(fail("Unknown API route.")));
  app.use("/api", api);

  mountLocalClips(app, { config });

  // The passage index is a plain JSON document (no envelope), exactly what the generator publishes to S3 data/index.json on
  // AWS: the frontend reads documents and does no processing (ReadWorks' technical guide).
  app.get(
    "/data/index.json",
    route(async (req, res) => {
      res.set("Cache-Control", "no-cache");
      res.json(await catalog.list());
    }),
  );

  // Generated files: an allow-list, so state.json and raw inputs are never served. sendFile supports Range (MP3 seeking).
  app.get("/data/:file", (req, res) => {
    if (!config.dataDir || !DATA_FILE.test(req.params.file)) return res.status(404).json(fail("File not found."));
    return res.sendFile(path.join(config.dataDir, req.params.file), { dotfiles: "deny", maxAge: 0 }, (err) => {
      if (err && !res.headersSent) res.status(404).json(fail("File not found."));
    });
  });

  if (config.webDist) {
    app.use(express.static(config.webDist, { index: false }));
    app.get(/^\/(?!api\/|data\/).*/, (req, res) => res.sendFile(path.join(config.webDist, "index.html")));
  }

  app.use(errorHandler(logger));
  return app;
}

