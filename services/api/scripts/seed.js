import { PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand } from "@aws-sdk/lib-dynamodb";
import { access, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { reviewOf, summarizePassage } from "../src/passageSummary.js";

const TIMING = /^([0-9a-f-]{36})\.timing\.json$/;

const exists = (file) => access(file).then(() => true, () => false);

/** The `source` field of raw/<id>.json, or "sample" when the file is missing or unreadable. */
const readSource = (file) => readFile(file, "utf8").then((t) => JSON.parse(t).source, () => "sample");

/** Publish data/index.json (newest first, same fields as GET /api/passages): the Library reads this document directly. */
async function publishIndex({ s3, bucket, summaries }) {
  const sorted = [...summaries].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  await s3.send(new PutObjectCommand({ Bucket: bucket, Key: "data/index.json", Body: gzipSync(JSON.stringify(sorted)), ContentType: "application/json", ContentEncoding: "gzip" }));
}

/** Upload every local passage (mp3 + timing) to S3 and write its PASSAGE summary item. Returns the ids seeded. */
export async function seed({ s3, ddb, bucket, tableName, dataDir, logger = console }) {
  const files = (await readdir(dataDir)).filter((f) => TIMING.test(f));
  const ids = [];
  const summaries = [];
  for (const file of files) {
    const id = file.match(TIMING)[1];
    const mp3 = path.join(dataDir, `${id}.mp3`);
    if (!(await exists(mp3))) {
      logger.warn(`skipping ${id}: no matching mp3`);
      continue;
    }
    const timingPath = path.join(dataDir, file);
    const [timingText, audio, { mtimeMs }, source] = await Promise.all([
      readFile(timingPath, "utf8"),
      readFile(mp3),
      stat(timingPath),
      readSource(path.join(dataDir, "raw", `${id}.json`)),
    ]);
    const timing = JSON.parse(timingText);
    await s3.send(new PutObjectCommand({ Bucket: bucket, Key: `data/${id}.mp3`, Body: audio, ContentType: "audio/mpeg" }));
    await s3.send(new PutObjectCommand({ Bucket: bucket, Key: `data/${id}.timing.json`, Body: gzipSync(timingText), ContentType: "application/json", ContentEncoding: "gzip" }));
    const cardsPath = path.join(dataDir, `${id}.cards.json`);
    if (await exists(cardsPath)) {
      // Small and read as-is by the browser: plain application/json, no gzip.
      await s3.send(new PutObjectCommand({ Bucket: bucket, Key: `data/${id}.cards.json`, Body: await readFile(cardsPath), ContentType: "application/json" }));
    }
    const item = { pk: "PASSAGE", sk: id, ...summarizePassage({ id, timing, mtimeMs, source }), metrics: timing.metrics ?? {}, ...(reviewOf(timing) && { review: reviewOf(timing) }) };
    await ddb.send(new PutCommand({ TableName: tableName, Item: item }));
    logger.info(`uploaded ${id}: ${item.title} (s3 data/${id}.mp3, data/${id}.timing.json; PASSAGE item)`);
    ids.push(id);
    summaries.push(summarizePassage({ id, timing, mtimeMs, source }));
  }
  if (summaries.length > 0) await publishIndex({ s3, bucket, summaries });
  await seedAb({ s3, bucket, dataDir, logger });
  const reportFile = path.join(dataDir, "quality-report.json");
  if (await exists(reportFile)) {
    const report = JSON.parse(await readFile(reportFile, "utf8"));
    await ddb.send(new PutCommand({ TableName: tableName, Item: { pk: "QUALITY", sk: "REPORT", report } }));
    logger.info("wrote QUALITY item from data/quality-report.json");
  }
  return ids;
}

const AB_MANIFEST = "manifest.json";
const AB_CLIP = /^[0-9a-f]{16}\.mp3$/;

/** Upload <dataDir>/ab/ (blind-test clips as audio/mpeg, manifest.json as application/json) to S3 (clips under data/ab/, the manifest under raw/ab/ so CloudFront can never serve the answer key). Returns the keys. */
export async function seedAb({ s3, bucket, dataDir, logger = console }) {
  const dir = path.join(dataDir, "ab");
  let names = [];
  try {
    names = await readdir(dir);
  } catch (err) {
    if (err.code !== "ENOENT") throw err;
  }
  const keys = [];
  for (const name of names.sort()) {
    const isManifest = name === AB_MANIFEST;
    if (!isManifest && !AB_CLIP.test(name)) {
      logger.warn(`skipping ab/${name}: not a clip or the manifest`);
      continue;
    }
    const Key = isManifest ? "raw/ab/manifest.json" : `data/ab/${name}`;
    await s3.send(new PutObjectCommand({ Bucket: bucket, Key, Body: await readFile(path.join(dir, name)), ContentType: isManifest ? "application/json" : "audio/mpeg" }));
    keys.push(Key);
  }
  if (keys.length > 0) logger.info(`uploaded ${keys.length} blind-test file(s) to s3 data/ab/`);
  return keys;
}

async function main(env, logger) {
  const { BUCKET: bucket, TABLE_NAME: tableName } = env;
  if (!bucket || !tableName) {
    logger.error("Set BUCKET and TABLE_NAME, for example: BUCKET=... TABLE_NAME=... node scripts/seed.js");
    return 1;
  }
  const dataDir = path.resolve(env.DATA_DIR ?? path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "data"));
  const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } });
  const ids = await seed({ s3: new S3Client({}), ddb, bucket, tableName, dataDir, logger });
  logger.info(`seeded ${ids.length} passage(s) into s3://${bucket} and table ${tableName}`);
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const out = { info: (m) => process.stdout.write(`${m}\n`), warn: (m) => process.stderr.write(`${m}\n`), error: (m) => process.stderr.write(`${m}\n`) };
  main(process.env, out).then(
    (code) => { process.exitCode = code; },
    (err) => { out.error(`seed failed: ${err.message}`); process.exitCode = 1; },
  );
}
