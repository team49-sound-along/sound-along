import { randomUUID } from "node:crypto";
import { DeleteCommand, GetCommand, PutCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { buildSet, isConditionalFailure, queryPartition, stripKeys } from "./dynamo.js";

const TTL_SECONDS = 7 * 24 * 60 * 60;
const ACTIVE_JOB_MAX_AGE_MS = 9 * 60 * 60 * 1000;
const LOCK_KEY = { pk: "LOCK", sk: "GENERATE_START" };
// Long enough to cover S3 put + StartExecution, short enough that a crashed request frees the lock quickly.
const LOCK_LEASE_MS = 15_000;

/** Async job registry in DynamoDB (JOB items with a 7-day TTL). Same interface as createJobStore, but every call returns a promise. */
export function createDynamoJobs({ client, tableName, now = Date.now }) {
  const key = (id) => ({ pk: "JOB", sk: id });
  const view = (item) => stripKeys(item, ["ttl"]);

  return {
    async create(title, { humanPassageId = null, chunks = 0 } = {}) {
      const job = {
        id: randomUUID(),
        title,
        status: "queued",
        step: "parse",
        passageId: null,
        humanPassageId,
        chunksDone: 0,
        chunksTotal: chunks, // a long document is narrated in this many internal chunks (0 = one run); the page shows progress and time left from these
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
    /**
     * Serialises "check the cap, then start a job" across Lambda instances with a short lease.
     * Returns a release function, or null when another request holds the lease. An expired lease counts as free.
     */
    async acquireStartLock() {
      const t = now();
      const owner = randomUUID();
      try {
        await client.send(
          new PutCommand({
            TableName: tableName,
            Item: { ...LOCK_KEY, owner, expiresAt: t + LOCK_LEASE_MS, ttl: Math.floor(t / 1000) + 3600 },
            ConditionExpression: "attribute_not_exists(pk) OR expiresAt < :now",
            ExpressionAttributeValues: { ":now": t },
          }),
        );
      } catch (err) {
        if (isConditionalFailure(err)) return null;
        throw err;
      }
      return async () => {
        try {
          await client.send(
            new DeleteCommand({
              TableName: tableName,
              Key: LOCK_KEY,
              ConditionExpression: "owner = :owner",
              ExpressionAttributeValues: { ":owner": owner },
            }),
          );
        } catch {
          // The lease expires on its own; failing to release must never fail the request.
        }
      };
    },
    async activeCount() {
      // A job that has not finished after 9 hours (longer than the state machine's timeout) is stuck, for example after a crash: it must not block new work.
      const cutoff = new Date(now() - ACTIVE_JOB_MAX_AGE_MS).toISOString();
      const pages = await queryPartition(client, tableName, "JOB", {
        filter: "#s IN (:queued, :running) AND startedAt > :cutoff",
        names: { "#s": "status" },
        values: { ":queued": "queued", ":running": "running", ":cutoff": cutoff },
        select: "COUNT",
      });
      return pages.reduce((total, page) => total + (page.Count ?? 0), 0);
    },
  };
}
