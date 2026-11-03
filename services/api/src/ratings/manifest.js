import { readFile } from "node:fs/promises";
import path from "node:path";
import { GetObjectCommand } from "@aws-sdk/client-s3";

export const TOKEN = /^[0-9a-f]{16}$/;
const CACHE_MS = 60_000;
const MANIFEST_KEY = "raw/ab/manifest.json";

/** Keep only well-formed clip entries, as new objects. Anything else in the manifest is ignored. */
export function cleanManifest(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c) => c && TOKEN.test(c.token) && typeof c.passageId === "string" && typeof c.kind === "string" && c.kind.length > 0)
    .map((c) => ({ token: c.token, passageId: c.passageId, title: typeof c.title === "string" ? c.title : "Untitled passage", kind: c.kind }));
}

/** Local manifest at <dataDir>/ab/manifest.json. read() -> clips[] (empty when the file is missing). Read on every call. */
export function createFileManifest(dataDir) {
  return {
    async read() {
      try {
        return cleanManifest(JSON.parse(await readFile(path.join(dataDir, "ab", "manifest.json"), "utf8")));
      } catch (err) {
        if (err.code === "ENOENT" || err instanceof SyntaxError) return [];
        throw err;
      }
    },
  };
}

/** S3 manifest (raw/ab/manifest.json) read through an injected client and cached for 60 s. A missing object is an empty manifest. */
export function createS3Manifest({ s3, bucket, now = Date.now, cacheMs = CACHE_MS }) {
  let cached = null; // { expires, clips }
  return {
    async read() {
      if (cached && cached.expires > now()) return cached.clips;
      let clips = [];
      try {
        const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: MANIFEST_KEY }));
        clips = cleanManifest(JSON.parse(await res.Body.transformToString()));
      } catch (err) {
        if (!(err?.name === "NoSuchKey" || err?.$metadata?.httpStatusCode === 404 || err instanceof SyntaxError)) throw err;
      }
      cached = { expires: now() + cacheMs, clips };
      return clips;
    },
  };
}
