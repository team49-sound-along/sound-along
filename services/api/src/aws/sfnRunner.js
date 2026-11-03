import { randomUUID } from "node:crypto";
import { PutObjectCommand } from "@aws-sdk/client-s3";
import { StartExecutionCommand } from "@aws-sdk/client-sfn";
import { HttpError } from "../http.js";
import { textToHtml } from "../validate.js";

const FRIENDLY_FAILURE = "We could not start audio generation right now. Please try again in a moment.";

/** Starts generation on AWS: raw input to S3, then a Step Functions execution (input shape in docs/AWS.md). */
export function createSfnRunner({ jobs, s3, sfn, bucket, stateMachineArn, logger = console }) {
  async function start({ title, text }) {
    const job = await jobs.create(title);
    const passageId = randomUUID();
    const rawKey = `raw/${passageId}.json`;
    try {
      await s3.send(
        new PutObjectCommand({
          Bucket: bucket,
          Key: rawKey,
          ContentType: "application/json",
          Body: JSON.stringify({ uuid: passageId, title, content: textToHtml(text), source: "generated" }),
        }),
      );
      await sfn.send(
        new StartExecutionCommand({
          stateMachineArn,
          name: job.id,
          input: JSON.stringify({ jobId: job.id, passageId, title, rawKey }),
        }),
      );
    } catch (err) {
      logger.error("could not start generation", { jobId: job.id, message: err?.message });
      await jobs.update(job.id, { status: "failed", error: FRIENDLY_FAILURE, finishedAt: new Date().toISOString() });
      throw new HttpError(503, FRIENDLY_FAILURE);
    }
    return (await jobs.update(job.id, { passageId })) ?? { ...job, passageId };
  }

  return { start };
}
