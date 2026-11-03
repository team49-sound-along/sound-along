import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { SFNClient } from "@aws-sdk/client-sfn";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import serverlessExpress from "@codegenie/serverless-express";
import { createApp } from "../app.js";
import { createDynamoCatalog } from "./dynamoCatalog.js";
import { createDynamoJobs } from "./dynamoJobs.js";
import { createDynamoStore } from "./dynamoStore.js";
import { createS3Recordings } from "./s3Recordings.js";
import { createS3Sources } from "./s3Sources.js";
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
      // Trust only the proxy hops we control (CloudFront). `true` would trust the left-most X-Forwarded-For entry,
      // which the caller can forge to dodge the rate limit. Verify the hop count after the first deploy (docs/AWS.md).
      trustProxy: Number.isInteger(Number(env.TRUSTED_PROXY_HOPS)) && Number(env.TRUSTED_PROXY_HOPS) > 0 ? Number(env.TRUSTED_PROXY_HOPS) : 1,
    },
    store: createDynamoStore({ client: clients.ddb, tableName }),
    catalog: createDynamoCatalog({ client: clients.ddb, tableName }),
    jobs,
    recordings: createS3Recordings({ s3: clients.s3, bucket, presign: clients.presign ?? ((command, opts) => getSignedUrl(clients.s3, command, opts)) }),
    sources: createS3Sources({ s3: clients.s3, bucket }),
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
