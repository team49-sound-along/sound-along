import { DeleteObjectsCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { DeleteCommand } from "@aws-sdk/lib-dynamodb";
import { gzipSync } from "node:zlib";
import { PASSAGE_FILE_SUFFIXES } from "../catalog.js";
import { splitReady } from "../readiness.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REVALIDATE = "public, max-age=0, must-revalidate";

/** One line of data/index.json, the same public fields the generator publishes (services/generator/summary.py index_entry). */
function indexEntry(p) {
  const { held, ...rest } = p; // eslint-disable-line no-unused-vars
  return { ...rest, pairId: p.pairId ?? null, language: p.language || "en", translations: p.translations ?? {}, translationOf: p.translationOf ?? null, series: p.series ?? null };
}

/**
 * Removes passages on AWS: their files under data/ (only the known per-passage names, never the index or the shared pictures), their PASSAGE items,
 * and then publishes data/index.json again from what is left, the way the generator does. `catalog` is the DynamoDB catalog (list + invalidate).
 * Needs s3:DeleteObject on the per-passage data/ names, s3:PutObject on data/index.json, and dynamodb:DeleteItem.
 */
export function createS3PassageRemoval({ s3, ddb, bucket, tableName, catalog }) {
  return {
    async remove(ids) {
      if (!ids.length || !ids.every((id) => UUID.test(id))) throw new Error("Invalid passage id.");
      const keys = ids.flatMap((id) => PASSAGE_FILE_SUFFIXES.map((suffix) => `data/${id}.${suffix}`));
      for (let i = 0; i < keys.length; i += 1000) {
        const res = await s3.send(new DeleteObjectsCommand({ Bucket: bucket, Delete: { Objects: keys.slice(i, i + 1000).map((Key) => ({ Key })), Quiet: true } }));
        if (res?.Errors?.length) throw new Error(`Could not delete ${res.Errors[0].Key}: ${res.Errors[0].Code ?? "error"}`);
      }
      for (const id of ids) await ddb.send(new DeleteCommand({ TableName: tableName, Key: { pk: "PASSAGE", sk: id } }));
      catalog.invalidate();
      const entries = splitReady(await catalog.list()).ready.map(indexEntry);
      await s3.send(new PutObjectCommand({ Bucket: bucket, Key: "data/index.json", Body: gzipSync(JSON.stringify(entries)), ContentType: "application/json", ContentEncoding: "gzip", CacheControl: REVALIDATE }));
    },
  };
}
