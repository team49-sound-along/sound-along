import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { SFNClient } from "@aws-sdk/client-sfn";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import serverlessExpress from "@codegenie/serverless-express";
import { createApp } from "../app.js";
import { createDynamoCatalog } from "./dynamoCatalog.js";
import { createDynamoJobs } from "./dynamoJobs.js";
import { createDynamoStore } from "./dynamoStore.js";
import { createSfnRunner } from "./sfnRunner.js";

/** Express app wired with the AWS adapters. Clients are injectable so tests never touch the network. */
export function buildAwsApp({ env, clients, logger = console }) {
  const { BUCKET: bucket, TABLE_NAME: tableName, STATE_MACHINE_ARN: stateMachineArn } = env;
  const jobs = createDynamoJobs({ client: clients.ddb, tableName });
  return createApp({
    config: {
      generationEnabled: (env.GENERATION_ENABLED ?? "true") === "true",
      generatePerMinute: Number(env.GENERATE_PER_MINUTE ?? 3),
      maxConcurrentJobs: Number(env.MAX_CONCURRENT_JOBS ?? 1),
      trustProxy: true, // behind CloudFront
    },
    store: createDynamoStore({ client: clients.ddb, tableName }),
    catalog: createDynamoCatalog({ client: clients.ddb, tableName }),
    jobs,
    runner: createSfnRunner({ jobs, s3: clients.s3, sfn: clients.sfn, bucket, stateMachineArn, logger }),
    logger,
  });
}

export function createHandler(env, clients) {
  return serverlessExpress({ app: buildAwsApp({ env, clients }) });
}

// Built once per container, reused across invocations.
export const handler = createHandler(process.env, {
  ddb: DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } }),
  s3: new S3Client({}),
  sfn: new SFNClient({}),
});
