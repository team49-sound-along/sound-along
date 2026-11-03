import { QueryCommand } from "@aws-sdk/lib-dynamodb";

/** Remove the table keys (and optional extra attributes) from a stored item without mutating it. */
export function stripKeys(item, extra = []) {
  const { pk, sk, ...rest } = item; // eslint-disable-line no-unused-vars
  return extra.reduce((acc, key) => {
    const { [key]: dropped, ...others } = acc; // eslint-disable-line no-unused-vars
    return others;
  }, rest);
}

/** Query every item in a partition, following LastEvaluatedKey. `extra` may add filter/select options. */
export async function queryPartition(client, tableName, pk, extra = {}) {
  const pages = [];
  let startKey;
  do {
    const res = await client.send(
      new QueryCommand({
        TableName: tableName,
        KeyConditionExpression: "pk = :pk",
        ExpressionAttributeValues: { ":pk": pk, ...extra.values },
        ...(extra.names && { ExpressionAttributeNames: extra.names }),
        ...(extra.filter && { FilterExpression: extra.filter }),
        ...(extra.select && { Select: extra.select }),
        ...(startKey && { ExclusiveStartKey: startKey }),
      }),
    );
    pages.push(res);
    startKey = res.LastEvaluatedKey;
  } while (startKey);
  return pages;
}

/** Build a SET expression for a plain patch object. */
export function buildSet(patch) {
  const keys = Object.keys(patch);
  return {
    UpdateExpression: `SET ${keys.map((_, i) => `#k${i} = :v${i}`).join(", ")}`,
    ExpressionAttributeNames: Object.fromEntries(keys.map((k, i) => [`#k${i}`, k])),
    ExpressionAttributeValues: Object.fromEntries(keys.map((k, i) => [`:v${i}`, patch[k]])),
  };
}

export const isConditionalFailure = (err) => err?.name === "ConditionalCheckFailedException";
