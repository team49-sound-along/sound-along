import { HttpError, ok, route } from "../http.js";
import { parseRecordingInput } from "../recordings/rules.js";

const KILLED = "Audio generation is switched off right now, so recordings cannot be uploaded.";
const TOO_BIG = "The recording is larger than 25 MB.";

/** Recording upload slot (POST /api/recordings), shared by local disk and S3 presigned uploads. */
export function recordingRoutes(api, { recordings, config, writeLimiter }) {
  api.post(
    "/recordings",
    route(async (req, res) => {
      if (!config.generationEnabled) throw new HttpError(503, KILLED);
      const input = parseRecordingInput(req.body);
      if (!writeLimiter(req.ip)) throw new HttpError(429, "You are uploading too quickly. Wait a minute and try again.");
      res.status(201).json(ok(await recordings.create(input)));
    }),
  );
}

/**
 * Local-only raw upload. Mounted BEFORE express.json so the body is streamed to disk, never parsed or buffered.
 * The 25 MB cap is enforced from Content-Length up front and again while streaming.
 */
export function mountLocalRecordingUpload(app, { recordings, config, writeLimiter, apiPrefix = "/api" }) {
  if (!recordings?.save) return;
  app.put(
    `${apiPrefix}/recordings/:id/content`,
    route(async (req, res) => {
      if (!config.generationEnabled) throw new HttpError(503, KILLED);
      if (!(await recordings.isIssued(req.params.id))) throw new HttpError(404, "That recording upload was not found. Start the upload again.");
      if (!writeLimiter(req.ip)) throw new HttpError(429, "You are uploading too quickly. Wait a minute and try again.");
      const declared = Number(req.headers["content-length"]);
      if (declared > recordings.maxBytes) {
        res.set("Connection", "close");
        throw new HttpError(413, TOO_BIG);
      }
      if (declared === 0) throw new HttpError(400, "The recording is empty.");
      try {
        await recordings.save(req.params.id, req);
      } catch (err) {
        if (err instanceof HttpError) res.set("Connection", "close");
        throw err;
      }
      res.status(204).end();
    }),
  );
}
