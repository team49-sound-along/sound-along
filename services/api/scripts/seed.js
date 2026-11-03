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

/** Upload every local passage (mp3 + timing) to S3 and write its PASSAGE summary item. Returns the ids seeded. */
export async function seed({ s3, ddb, bucket, tableName, dataDir, logger = console }) {
  const files = (await readdir(dataDir)).filter((f) => TIMING.test(f));
  const ids = [];
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
    const item = { pk: "PASSAGE", sk: id, ...summarizePassage({ id, timing, mtimeMs, source }), metrics: timing.metrics ?? {}, ...(reviewOf(timing) && { review: reviewOf(timing) }) };
    await ddb.send(new PutCommand({ TableName: tableName, Item: item }));
    logger.info(`uploaded ${id}: ${item.title} (s3 data/${id}.mp3, data/${id}.timing.json; PASSAGE item)`);
    ids.push(id);
  }
  const reportFile = path.join(dataDir, "quality-report.json");
  if (await exists(reportFile)) {
    const report = JSON.parse(await readFile(reportFile, "utf8"));
    await ddb.send(new PutCommand({ TableName: tableName, Item: { pk: "QUALITY", sk: "REPORT", report } }));
    logger.info("wrote QUALITY item from data/quality-report.json");
  }
  return ids;
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
