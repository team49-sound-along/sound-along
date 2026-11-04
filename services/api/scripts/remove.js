// Remove passages from a deployed site (demo clean-up): their files in S3, their summary in DynamoDB, and their line in the Library list (data/index.json).
// DRY RUN by default: it only lists what it would delete. Add --apply to delete.
//
//   BUCKET=... TABLE_NAME=... node scripts/remove.js <passage id> [<passage id> ...]            # list
//   BUCKET=... TABLE_NAME=... node scripts/remove.js --apply <passage id> [<passage id> ...]    # delete
//
// Pass the id of every passage you mean to remove, including its translation (a translation is a passage of its own): a passage whose translation is left
// behind keeps an "Also in ..." link that leads nowhere, so this refuses to run when a link would be left dangling.
import { DeleteObjectsCommand, ListObjectsV2Command, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DeleteCommand, DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { readIndex } from "./seed.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REVALIDATE = "public, max-age=0, must-revalidate";

async function keysOf({ s3, bucket, id }) {
  const keys = [];
  let token;
  do {
    const page = await s3.send(new ListObjectsV2Command({ Bucket: bucket, Prefix: `data/${id}.`, ...(token ? { ContinuationToken: token } : {}) }));
    keys.push(...(page.Contents ?? []).map((o) => o.Key));
    token = page.NextContinuationToken;
  } while (token);
  return keys;
}

/** Returns { problems, titles, keys }. With apply=false nothing is changed. */
export async function removePassages({ s3, ddb, bucket, tableName, ids, apply = false, logger = console }) {
  const bad = ids.filter((id) => !UUID.test(id));
  if (!ids.length || bad.length) return { problems: [bad.length ? `not a passage id: ${bad[0]}` : "give at least one passage id"], titles: [], keys: [] };
  const index = await readIndex({ s3, bucket });
  const byId = new Map(index.map((p) => [p.id, p]));
  const removed = new Set(ids);
  const problems = [];
  for (const id of ids) if (!byId.has(id)) problems.push(`${id} is not in the Library list (wrong id?)`);
  for (const p of index) {
    if (removed.has(p.id)) continue;
    for (const target of [...Object.values(p.translations ?? {}), p.translationOf, p.pairId].filter(Boolean)) {
      if (removed.has(target)) problems.push(`"${p.title}" (${p.id}) is linked to ${target}, which is being removed: remove it too, or neither`);
    }
  }
  for (const id of ids) {
    const p = byId.get(id);
    for (const target of [...Object.values(p?.translations ?? {}), p?.translationOf, p?.pairId].filter(Boolean)) {
      if (!removed.has(target)) problems.push(`"${p.title}" (${id}) is linked to ${target}: add that id too`);
    }
  }
  const keys = [];
  for (const id of ids) keys.push(...(await keysOf({ s3, bucket, id })));
  const titles = ids.map((id) => `${byId.get(id)?.title ?? "?"} (${id})`);
  if (problems.length) return { problems: [...new Set(problems)], titles, keys };
  logger.info(`${apply ? "removing" : "would remove"}: ${titles.join("; ")}`);
  logger.info(`${keys.length} file(s) in s3 data/, ${ids.length} DynamoDB item(s), and ${ids.length} line(s) of the Library list`);
  if (!apply) return { problems: [], titles, keys };
  for (let i = 0; i < keys.length; i += 1000) {
    await s3.send(new DeleteObjectsCommand({ Bucket: bucket, Delete: { Objects: keys.slice(i, i + 1000).map((Key) => ({ Key })) } }));
  }
  for (const id of ids) await ddb.send(new DeleteCommand({ TableName: tableName, Key: { pk: "PASSAGE", sk: id } }));
  const rest = index.filter((p) => !removed.has(p.id));
  await s3.send(new PutObjectCommand({ Bucket: bucket, Key: "data/index.json", Body: gzipSync(JSON.stringify(rest)), ContentType: "application/json", ContentEncoding: "gzip", CacheControl: REVALIDATE }));
  return { problems: [], titles, keys };
}

async function main(env, argv, logger) {
  const { BUCKET: bucket, TABLE_NAME: tableName } = env;
  if (!bucket || !tableName) {
    logger.error("Set BUCKET and TABLE_NAME, for example: BUCKET=... TABLE_NAME=... node scripts/remove.js <passage id>");
    return 1;
  }
  const apply = argv.includes("--apply");
  const ids = argv.filter((a) => a !== "--apply");
  const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}));
  const { problems } = await removePassages({ s3: new S3Client({}), ddb, bucket, tableName, ids, apply, logger });
  if (problems.length) {
    problems.forEach((p) => logger.error(p));
    return 1;
  }
  if (!apply) logger.info("Nothing was changed. Add --apply to delete.");
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const out = { info: (m) => process.stdout.write(`${m}\n`), warn: (m) => process.stderr.write(`${m}\n`), error: (m) => process.stderr.write(`${m}\n`) };
  main(process.env, process.argv.slice(2), out).then(
    (code) => { process.exitCode = code; },
    (err) => { out.error(`remove failed: ${err.message}`); process.exitCode = 1; },
  );
}
