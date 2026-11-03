import { randomUUID } from "node:crypto";
import { DeleteCommand, GetCommand, PutCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { CLASSES, EVENT_KEY } from "../stores/fileStore.js";
import { buildSet, isConditionalFailure, queryPartition, stripKeys } from "./dynamo.js";

/** Assignments and event totals in the DynamoDB single table (docs/AWS.md). `client` is a DynamoDBDocumentClient. */
export function createDynamoStore({ client, tableName }) {
  const key = (pk, sk) => ({ pk, sk });

  return {
    async listClasses() {
      return CLASSES;
    },
    async listAssignments() {
      const pages = await queryPartition(client, tableName, "ASSIGNMENT");
      return pages
        .flatMap((page) => page.Items ?? [])
        .map((item) => stripKeys(item))
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    async createAssignment(input) {
      const assignment = { id: randomUUID(), ...input, createdAt: new Date().toISOString() };
      await client.send(new PutCommand({ TableName: tableName, Item: { ...key("ASSIGNMENT", assignment.id), ...assignment } }));
      return assignment;
    },
    async updateAssignment(id, patch) {
      try {
        const res = await client.send(
          new UpdateCommand({
            TableName: tableName,
            Key: key("ASSIGNMENT", id),
            ConditionExpression: "attribute_exists(pk)",
            ReturnValues: "ALL_NEW",
            ...buildSet(patch),
          }),
        );
        return stripKeys(res.Attributes);
      } catch (err) {
        if (isConditionalFailure(err)) return null;
        throw err;
      }
    },
    async deleteAssignment(id) {
      const res = await client.send(
        new DeleteCommand({ TableName: tableName, Key: key("ASSIGNMENT", id), ReturnValues: "ALL_OLD" }),
      );
      return Boolean(res.Attributes);
    },
    async recordEvent(type) {
      await client.send(
        new UpdateCommand({
          TableName: tableName,
          Key: key("EVENTS", "TOTALS"),
          UpdateExpression: "ADD #n :one",
          ExpressionAttributeNames: { "#n": EVENT_KEY[type] },
          ExpressionAttributeValues: { ":one": 1 },
        }),
      );
    },
    async eventCounts() {
      const res = await client.send(new GetCommand({ TableName: tableName, Key: key("EVENTS", "TOTALS") }));
      const item = res.Item ?? {};
      return { plays: item.plays ?? 0, wordTaps: item.wordTaps ?? 0, completions: item.completions ?? 0 };
    },
  };
}
