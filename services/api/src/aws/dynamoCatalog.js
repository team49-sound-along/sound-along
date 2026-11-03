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
    async list() {
      return (await items())
        .map((item) => stripKeys({ id: item.sk, ...item }, ["metrics"]))
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    async timings() {
      return (await items()).map((item) => ({ engine: item.engine, metrics: item.metrics ?? {} }));
    },
    /** Measured quality report (QUALITY item written by scripts/seed.js), or null. */
    async qualityReport() {
      const { Item } = await client.send(new GetCommand({ TableName: tableName, Key: { pk: "QUALITY", sk: "REPORT" } }));
      return Item?.report ?? null;
    },
  };
}
