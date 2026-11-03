import express from "express";
import path from "node:path";
import { HttpError, errorHandler, fail, ok, route } from "./http.js";
import { buildInsights } from "./insights.js";
import { createRateLimiter } from "./rateLimit.js";
import { parseAssignmentInput, parseEvent, parseGenerateInput, parseToggle } from "./validate.js";

const DATA_FILE = /^[0-9a-f-]{36}\.(mp3|timing\.json)$/;

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
 */
export function createApp({ store, catalog, jobs, runner, config, logger = console }) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", config.trustProxy ?? false);
  app.use((req, res, next) => {
    res.set(SECURITY_HEADERS);
    next();
  });
  app.use(express.json({ limit: "64kb" }));

  const generateLimiter = createRateLimiter({ max: config.generatePerMinute, windowMs: 60_000 });

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

  api.post(
    "/generate",
    route(async (req, res) => {
      if (!config.generationEnabled) {
        throw new HttpError(503, "Audio generation is switched off right now. Pre-generated passages are still available.");
      }
      const input = parseGenerateInput(req.body);
      if (!generateLimiter(req.ip)) throw new HttpError(429, "You are generating too quickly. Wait a minute and try again.");
      // The cap check and the job start must be one atomic step, or parallel requests all pass the check.
      const release = await jobs.acquireStartLock();
      if (!release) throw new HttpError(429, "Another passage is being generated. Try again in a moment.");
      try {
        if ((await jobs.activeCount()) >= config.maxConcurrentJobs) {
          throw new HttpError(429, "Another passage is being generated. Try again in a moment.");
        }
        const job = await runner.start(input);
        res.status(202).json(ok({ jobId: job.id }));
      } finally {
        await release();
      }
    }),
  );

  api.get(
    "/jobs/:id",
    route(async (req, res) => {
      const job = await jobs.get(req.params.id);
      if (!job) return res.status(404).json(fail("That job was not found."));
      return res.json(ok(job));
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
      const [timings, assignments, events, qualityReport] = await Promise.all([
        catalog.timings(),
        store.listAssignments(),
        store.eventCounts(),
        catalog.qualityReport?.() ?? null,
      ]);
      res.json(ok(buildInsights({ timings, assignments, events, qualityReport })));
    }),
  );

  api.use((req, res) => res.status(404).json(fail("Unknown API route.")));
  app.use("/api", api);

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

