import { randomUUID } from "node:crypto";
import { createWriteStream } from "node:fs";
import { access, mkdir, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { HttpError } from "../http.js";
import { MAX_RECORDING_BYTES, UUID } from "./rules.js";

const present = (file) => access(file).then(() => true, () => false);

/** Counts bytes and fails the pipeline as soon as the limit is crossed, so nothing is buffered or fully written. */
function byteLimit(maxBytes) {
  let seen = 0;
  return new Transform({
    transform(chunk, enc, cb) {
      seen += chunk.length;
      if (seen > maxBytes) return cb(new HttpError(413, "The recording is larger than 25 MB."));
      return cb(null, chunk);
    },
  });
}

/** Recordings on local disk: <dataDir>/raw/<id>.audio. An id is "known" once POST /api/recordings issued it. */
export function createLocalRecordings({ dataDir, maxBytes = MAX_RECORDING_BYTES }) {
  const rawDir = path.join(dataDir, "raw");
  const audioFile = (id) => path.join(rawDir, `${id}.audio`);
  const issuedFile = (id) => path.join(rawDir, `${id}.recording.json`);

  return {
    maxBytes,
    async create({ filename, contentType, size }) {
      const recordingId = randomUUID();
      await mkdir(rawDir, { recursive: true });
      await writeFile(issuedFile(recordingId), JSON.stringify({ filename, contentType, size, createdAt: new Date().toISOString() }));
      return { recordingId, upload: { method: "PUT", url: `/api/recordings/${recordingId}/content`, headers: { "Content-Type": contentType } } };
    },
    /** True once audio bytes have been uploaded for this id. */
    async exists(id) {
      return UUID.test(id) && present(audioFile(id));
    },
    /** True when the id was issued by create(). */
    async isIssued(id) {
      return UUID.test(id) && present(issuedFile(id));
    },
    ref: (id) => ({ path: audioFile(id) }),
    /** Stream `source` to disk. Rejects with a 413 HttpError past the limit; partial files are removed. */
    async save(id, source) {
      const part = `${audioFile(id)}.${process.pid}.part`;
      try {
        await pipeline(source, byteLimit(maxBytes), createWriteStream(part));
        await rename(part, audioFile(id));
      } catch (err) {
        await unlink(part).catch(() => undefined);
        throw err;
      }
    },
  };
}
