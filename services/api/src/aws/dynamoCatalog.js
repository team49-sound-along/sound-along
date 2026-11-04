import { GetCommand } from "@aws-sdk/lib-dynamodb";
import { queryPartition, stripKeys } from "./dynamo.js";

const CACHE_MS = 30_000;

/** Passage catalog over PASSAGE summary items. Reads are cached for 30 s to keep DynamoDB traffic low. */
export function createDynamoCatalog({ client, tableName, now = Date.now, cacheMs = CACHE_MS }) {
  let cached = null; // { expires, items }

  async function items() {
    if (cached && cached.expires > now()) return cached.items;
    const pages = await queryPartition(client, tableName, "PASSAGE");
    const loaded = pages.flatMap((page) => page.Items ?? []);
    cached = { expires: now() + cacheMs, items: loaded };
    return loaded;
  }

  return {
    /** Drop the cached items, so the next read sees a change made just now (a passage deleted from the Library). */
    invalidate() {
      cached = null;
    },
    async list() {
      return (await items())
        .map((item) => stripKeys({ id: item.sk, ...item, language: item.language === "es" ? "es" : "en" }, ["metrics", "review"]))
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    async timings() {
      return (await items()).map((item) => ({ engine: item.engine, metrics: item.metrics ?? {} }));
    },
    /** Passages carrying ASR review suspects (the PASSAGE item's `review` field). */
    async reviewSources() {
      return (await items()).filter((item) => item.review).map((item) => ({ id: item.sk, title: item.title, review: item.review }));
    },
    /** Measured quality report (QUALITY item written by scripts/seed.js), or null. */
    async qualityReport() {
      const { Item } = await client.send(new GetCommand({ TableName: tableName, Key: { pk: "QUALITY", sk: "REPORT" } }));
      return Item?.report ?? null;
    },
  };
}
