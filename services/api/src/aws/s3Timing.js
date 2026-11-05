import { GetObjectCommand } from "@aws-sdk/client-s3";
import { gunzipSync } from "node:zlib";

const CACHE_MAX = 40;
const UUID = /^[0-9a-f-]{36}$/;
const isMissing = (err) => err?.name === "NoSuchKey" || err?.$metadata?.httpStatusCode === 404;

/**
 * Reads one passage's timing document (data/<id>.timing.json) so the server can look up the text of a word position. Only the words are
 * kept, in a small cache (at most CACHE_MAX passages, oldest dropped first). Needs s3:GetObject on data/*.timing.json and nothing wider.
 */
export function createS3Timing({ s3, bucket }) {
  const cache = new Map();
  return {
    async timing(id) {
      if (!UUID.test(String(id))) return null;
      if (cache.has(id)) return cache.get(id);
      let doc;
      try {
        const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: `data/${id}.timing.json` }));
        const bytes = Buffer.from(await res.Body.transformToByteArray());
        // Timing files are stored gzip-compressed (ContentEncoding gzip), and S3 hands the bytes back as stored: unpack them before reading.
        const full = JSON.parse((bytes[0] === 0x1f && bytes[1] === 0x8b ? gunzipSync(bytes) : bytes).toString("utf8"));
        doc = { language: full.language, words: (full.words ?? []).map((w) => ({ i: w.i, text: w.text })) };
      } catch (err) {
        if (isMissing(err) || err instanceof SyntaxError) return null;
        throw err;
      }
      if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value);
      cache.set(id, doc);
      return doc;
    },
  };
}
