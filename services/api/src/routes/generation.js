import { randomUUID } from "node:crypto";
import { HttpError, ok, route } from "../http.js";
import { toPronunciationMap } from "../pronunciations.js";
import { UUID } from "../recordings/rules.js";
import { effectiveSettings } from "../settings.js";
import { parseGenerateInput } from "../validate.js";

const BUSY = "Another passage is being generated. Try again in a moment.";

/**
 * POST /generate and POST /passages/:id/regenerate. Both share one kill switch, one rate limiter and one
 * "check the cap, then start" lock, so they can never run more jobs than MAX_CONCURRENT_JOBS together.
 */
export function generationRoutes(api, { store, jobs, runner, recordings, sources, config, generateLimiter }) {
  /** The settings and pronunciations in force right now, copied into the job so the generator needs no database. */
  async function snapshot() {
    const [stored, fixes] = await Promise.all([store.getSettings?.() ?? null, store.listPronunciations?.() ?? []]);
    return { settings: effectiveSettings(stored), pronunciations: toPronunciationMap(fixes) };
  }

  /** Kill switch, then `prepare` (validation), then limiter, lock and cap, then `build` -> runner.start. */
  async function guarded(req, res, { prepare, build }) {
    if (!config.generationEnabled) {
      throw new HttpError(503, "Audio generation is switched off right now. Pre-generated passages are still available.");
    }
    const parsed = prepare(req);
    if (!generateLimiter(req.ip)) throw new HttpError(429, "You are generating too quickly. Wait a minute and try again.");
    // The cap check and the job start must be one atomic step, or parallel requests all pass the check.
    const release = await jobs.acquireStartLock();
    if (!release) throw new HttpError(429, BUSY);
    try {
      if ((await jobs.activeCount()) >= config.maxConcurrentJobs) throw new HttpError(429, BUSY);
      const job = await runner.start(await build(parsed));
      res.status(202).json(ok({ jobId: job.id }));
    } finally {
      await release();
    }
  }

  api.post(
    "/generate",
    route((req, res) =>
      guarded(req, res, {
        prepare: (r) => parseGenerateInput(r.body),
        async build({ title, text, recordingId }) {
          if (recordingId && !(await recordings?.exists(recordingId))) {
            throw new HttpError(400, "We could not find that recording. Upload it again and retry.");
          }
          return {
            title,
            text,
            recordingId,
            humanPassageId: recordingId ? randomUUID() : null,
            ...(await snapshot()),
          };
        },
      }),
    ),
  );

  api.post(
    "/passages/:id/regenerate",
    route((req, res) =>
      guarded(req, res, {
        prepare: (r) => r.params.id,
        async build(passageId) {
          const missing = new HttpError(404, "This passage has no saved source text, so it cannot be regenerated.");
          const stored = UUID.test(passageId) ? await sources?.read(passageId) : null;
          if (!stored || typeof stored.title !== "string" || typeof stored.content !== "string") throw missing;
          return {
            passageId,
            title: stored.title,
            content: stored.content,
            source: stored.source ?? "generated",
            recording: stored.recording ?? null,
            humanPassageId: stored.recording ? (stored.humanPassageId ?? null) : null,
            ...(await snapshot()),
          };
        },
      }),
    ),
  );
}
