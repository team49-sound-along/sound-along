import { randomUUID } from "node:crypto";
import { GetCommand, PutCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { buildSet, isConditionalFailure, queryPartition, stripKeys } from "./dynamo.js";

const TTL_SECONDS = 7 * 24 * 60 * 60;

/** Async job registry in DynamoDB (JOB items with a 7-day TTL). Same interface as createJobStore, but every call returns a promise. */
export function createDynamoJobs({ client, tableName, now = Date.now }) {
  const key = (id) => ({ pk: "JOB", sk: id });
  const view = (item) => stripKeys(item, ["ttl"]);

  return {
    async create(title) {
      const job = {
        id: randomUUID(),
        title,
        status: "queued",
        step: "parse",
        passageId: null,
        error: null,
        metrics: null,
        startedAt: new Date(now()).toISOString(),
        finishedAt: null,
      };
      const ttl = Math.floor(now() / 1000) + TTL_SECONDS;
      await client.send(new PutCommand({ TableName: tableName, Item: { ...key(job.id), ...job, ttl } }));
      return job;
    },
    async get(id) {
      const res = await client.send(new GetCommand({ TableName: tableName, Key: key(id) }));
      return res.Item ? view(res.Item) : null;
    },
    async update(id, patch) {
      try {
        const res = await client.send(
          new UpdateCommand({
            TableName: tableName,
            Key: key(id),
            ConditionExpression: "attribute_exists(pk)",
            ReturnValues: "ALL_NEW",
            ...buildSet(patch),
          }),
        );
        return view(res.Attributes);
      } catch (err) {
        if (isConditionalFailure(err)) return null;
        throw err;
      }
    },
    async activeCount() {
      const pages = await queryPartition(client, tableName, "JOB", {
        filter: "#s IN (:queued, :running)",
        names: { "#s": "status" },
        values: { ":queued": "queued", ":running": "running" },
        select: "COUNT",
      });
      return pages.reduce((total, page) => total + (page.Count ?? 0), 0);
    },
  };
}
