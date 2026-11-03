import { randomUUID } from "node:crypto";
import { PutCommand } from "@aws-sdk/lib-dynamodb";
import { queryPartition, stripKeys } from "./dynamo.js";

/** Ratings as RATING/{uuid} items in the single table. */
export function createDynamoRatingMethods({ client, tableName }) {
  return {
    async addRating(rating) {
      await client.send(new PutCommand({ TableName: tableName, Item: { pk: "RATING", sk: randomUUID(), ...rating } }));
    },
    async listRatings() {
      const pages = await queryPartition(client, tableName, "RATING");
      return pages.flatMap((page) => page.Items ?? []).map((item) => stripKeys(item));
    },
  };
}
