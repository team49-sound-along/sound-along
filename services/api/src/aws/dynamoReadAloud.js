import { QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { buildSet, isConditionalFailure, queryPartition } from "./dynamo.js";
import { NO_CLASS, READERS_PER_CLASS, READER_SESSIONS, RETENTION_DAYS, readerSession } from "../stores/fileReadAloud.js";
import { weekStart } from "../readAloud/weeks.js";

export const SUMMARY_PK = "RA_SUMMARY";
export const WEEK_PK = "RA_WEEK";
export const READER_PK = "RA_READER#";
export const SUMMARY_LIMIT = 500; // one small item per passage and class; a capped read, never a scan
export const WEEK_LIMIT = 1000; // weeks x passages x classes since the first requested week
const wordsPk = (passageId) => `RA_WORDS#${passageId}`;
const WORD_ATTR = /^([sd])_(\d+)$/;

/** Flat s_<position> / d_<position> attributes back to { position: { s, d } }. */
function wordsOf(item) {
  const words = {};
  for (const [attr, count] of Object.entries(item)) {
    const m = WORD_ATTR.exec(attr);
    if (m) words[m[2]] = { ...words[m[2]], [m[1]]: count };
  }
  return words;
}

/**
 * Read-aloud counters and class switches in the single table. Counters only, no per-session item:
 *   RA_SUMMARY / <passage>#<class>   sessions, finished, retried   (one small query feeds the tiles)
 *   RA_WORDS#<passage> / <class>     s_<position>, d_<position>    (read only for the one passage a teacher opens)
 *   CLASSSETTINGS / <class|DEFAULT>  mic, share
 * Both counter items carry `ttl` (the table's expiry attribute), renewed on every write, so unused counters expire.
 * ADD works on top-level attributes only (it fails on a map that does not exist yet), hence the flat s_/d_ names.
 */
export function createDynamoReadAloudMethods({ client, tableName, now = Date.now }) {
  const expiry = () => Math.floor(now() / 1000) + RETENTION_DAYS * 86_400;
  const wordAdds = (flags) => flags.map(({ i, kind }) => `${kind === "skipped" ? "s" : "d"}_${i}`);

  /** SET updatedAt/ttl and ADD one to each named counter attribute. */
  async function send(pk, sk, counters, stamp, extraSet = "", extraValues = {}) {
    const names = { "#u": "updatedAt", "#t": "ttl" };
    const adds = counters.map((attr, n) => {
      names[`#w${n}`] = attr;
      return `#w${n} :one`;
    });
    await client.send(
      new UpdateCommand({
        TableName: tableName,
        Key: { pk, sk },
        UpdateExpression: `SET #u = :u, #t = :t${extraSet}${adds.length ? ` ADD ${adds.join(", ")}` : ""}`,
        ExpressionAttributeNames: { ...names, ...(extraSet && { "#s": "sessions" }) },
        ExpressionAttributeValues: { ":u": stamp, ":t": expiry(), ...(adds.length && { ":one": 1 }), ...extraValues },
      }),
    );
  }

  /** A reader's item: the last sessions as a list (appended, then trimmed to READER_SESSIONS) plus the same flat miss counters. */
  async function recordReader(result, key, stamp) {
    const pk = `${READER_PK}${key}`;
    const sk = `${result.readerCode}#${result.passageId}`;
    await send(pk, sk, wordAdds(result.words), stamp, ", #s = list_append(if_not_exists(#s, :empty), :new)", { ":empty": [], ":new": [readerSession(result, now())] });
    try {
      await client.send(
        new UpdateCommand({
          TableName: tableName,
          Key: { pk, sk },
          UpdateExpression: "REMOVE #s[0]",
          ConditionExpression: "size(#s) > :max",
          ExpressionAttributeNames: { "#s": "sessions" },
          ExpressionAttributeValues: { ":max": READER_SESSIONS },
        }),
      );
    } catch (err) {
      if (!isConditionalFailure(err)) throw err;
    }
  }

  return {
    async recordReadAloud(result) {
      const key = result.classId ?? NO_CLASS;
      const stamp = new Date(now()).toISOString();
      await client.send(
        new UpdateCommand({
          TableName: tableName,
          Key: { pk: SUMMARY_PK, sk: `${result.passageId}#${key}` },
          UpdateExpression: "SET #u = :u, #t = :t ADD #n :one, #f :f, #r :r",
          ExpressionAttributeNames: { "#u": "updatedAt", "#t": "ttl", "#n": "sessions", "#f": "finished", "#r": "retried" },
          ExpressionAttributeValues: { ":u": stamp, ":t": expiry(), ":one": 1, ":f": result.finished ? 1 : 0, ":r": result.retried > 0 ? 1 : 0 },
        }),
      );
      await client.send(
        new UpdateCommand({
          TableName: tableName,
          Key: { pk: WEEK_PK, sk: `${weekStart(now())}#${result.passageId}#${key}` },
          UpdateExpression: "SET #t = :t ADD #n :one, #f :f, #r :r",
          ExpressionAttributeNames: { "#t": "ttl", "#n": "sessions", "#f": "finished", "#r": "retried" },
          ExpressionAttributeValues: { ":t": expiry(), ":one": 1, ":f": result.finished ? 1 : 0, ":r": result.retried > 0 ? 1 : 0 },
        }),
      );
      if (result.words.length > 0) await send(wordsPk(result.passageId), key, wordAdds(result.words), stamp);
      if (result.readerCode) await recordReader(result, key, stamp);
    },
    async readAloudWeeks(fromWeek) {
      const res = await client.send(
        new QueryCommand({
          TableName: tableName,
          KeyConditionExpression: "pk = :pk AND sk >= :from",
          ExpressionAttributeValues: { ":pk": WEEK_PK, ":from": fromWeek },
          Limit: WEEK_LIMIT,
        }),
      );
      return (res.Items ?? []).map((item) => {
        const [week, passageId, key] = item.sk.split("#");
        return { week, passageId, classId: key === NO_CLASS ? null : key, sessions: item.sessions ?? 0, finished: item.finished ?? 0, retried: item.retried ?? 0 };
      });
    },
    async readAloudReaders(classId) {
      const res = await client.send(
        new QueryCommand({
          TableName: tableName,
          KeyConditionExpression: "pk = :pk",
          ExpressionAttributeValues: { ":pk": `${READER_PK}${classId ?? NO_CLASS}` },
          Limit: READERS_PER_CLASS,
        }),
      );
      return (res.Items ?? []).map((item) => {
        const [code, passageId] = item.sk.split("#");
        return { code, passageId, sessions: item.sessions ?? [], words: wordsOf(item) };
      });
    },
    async readAloudSummaries() {
      const res = await client.send(
        new QueryCommand({ TableName: tableName, KeyConditionExpression: "pk = :pk", ExpressionAttributeValues: { ":pk": SUMMARY_PK }, Limit: SUMMARY_LIMIT }),
      );
      return (res.Items ?? []).map((item) => {
        const [passageId, key] = item.sk.split("#");
        return { passageId, classId: key === NO_CLASS ? null : key, sessions: item.sessions ?? 0, finished: item.finished ?? 0, retried: item.retried ?? 0 };
      });
    },
    async readAloudWords(passageId) {
      const pages = await queryPartition(client, tableName, wordsPk(passageId));
      const summaries = await this.readAloudSummaries();
      return pages
        .flatMap((p) => p.Items ?? [])
        .map((item) => {
          const classId = item.sk === NO_CLASS ? null : item.sk;
          const sessions = summaries.find((s) => s.passageId === passageId && s.classId === classId)?.sessions ?? 0;
          return { passageId, classId, sessions, words: wordsOf(item) };
        });
    },
    async getClassSettings() {
      const pages = await queryPartition(client, tableName, "CLASSSETTINGS");
      return Object.fromEntries(
        pages.flatMap((p) => p.Items ?? []).map(({ sk, mic, share }) => [sk, { ...(mic !== undefined && { mic }), ...(share !== undefined && { share }) }]),
      );
    },
    async putClassSettings(key, patch) {
      await client.send(new UpdateCommand({ TableName: tableName, Key: { pk: "CLASSSETTINGS", sk: key }, ...buildSet(patch) }));
    },
  };
}
