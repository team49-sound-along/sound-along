import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { S3Client } from "@aws-sdk/client-s3";
import { SFNClient } from "@aws-sdk/client-sfn";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";
import { createApp } from "../app.js";
import { createS3Manifest } from "../ratings/manifest.js";
import { createDynamoCatalog } from "./dynamoCatalog.js";
import { createDynamoJobs } from "./dynamoJobs.js";
import { createDynamoStore } from "./dynamoStore.js";
import { createS3Recordings } from "./s3Recordings.js";
import { createS3Sources } from "./s3Sources.js";
import { createSfnRunner } from "./sfnRunner.js";

/**
 * Trust only the proxy hops we control (CloudFront). `true` would trust the left-most X-Forwarded-For entry,
 * which the caller can forge to dodge the rate limit. One hop (CloudFront) is right for both the Lambda and VM origins.
 */
function trustedProxyHops(env) {
  const hops = Number(env.TRUSTED_PROXY_HOPS);
  return Number.isInteger(hops) && hops > 0 ? hops : 1;
}

/**
 * Express app wired with the AWS adapters. Shared by the Lambda handler and the VM server.
 * `clients` ({ ddb, s3, sfn, presign? }) are injectable so tests never touch the network.
 */
export function createAwsApp(env, clients, logger = console) {
  const { BUCKET: bucket, TABLE_NAME: tableName, STATE_MACHINE_ARN: stateMachineArn } = env;
  const jobs = createDynamoJobs({ client: clients.ddb, tableName });
  return createApp({
    config: {
      generationEnabled: (env.GENERATION_ENABLED ?? "true") === "true",
      generatePerMinute: Number(env.GENERATE_PER_MINUTE ?? 3),
      maxConcurrentJobs: Number(env.MAX_CONCURRENT_JOBS ?? 1),
      trustProxy: trustedProxyHops(env),
    },
    store: createDynamoStore({ client: clients.ddb, tableName }),
    catalog: createDynamoCatalog({ client: clients.ddb, tableName }),
    jobs,
    recordings: createS3Recordings({ s3: clients.s3, bucket, presign: clients.presign ?? ((command, opts) => getSignedUrl(clients.s3, command, opts)) }),
    sources: createS3Sources({ s3: clients.s3, bucket }),
    manifest: createS3Manifest({ s3: clients.s3, bucket }),
    runner: createSfnRunner({ jobs, s3: clients.s3, sfn: clients.sfn, bucket, stateMachineArn, logger }),
    logger,
  });
}

/** Real SDK clients. Region and credentials come from the environment (Lambda role or EC2 instance profile). */
export function createAwsClients() {
  return {
    ddb: DynamoDBDocumentClient.from(new DynamoDBClient({}), { marshallOptions: { removeUndefinedValues: true } }),
    s3: new S3Client({}),
    sfn: new SFNClient({}),
  };
}
