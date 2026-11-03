import { randomUUID } from "node:crypto";
import { PutObjectCommand } from "@aws-sdk/client-s3";
import { StartExecutionCommand } from "@aws-sdk/client-sfn";
import { HttpError } from "../http.js";
import { buildJobInput } from "../jobs/jobInput.js";
import { recordingKey } from "../recordings/rules.js";
import { textToHtml } from "../validate.js";

const FRIENDLY_FAILURE = "We could not start audio generation right now. Please try again in a moment.";

/**
 * Starts generation on AWS: job input to S3 (raw/{passageId}.json), then a Step Functions execution (docs/AWS.md).
 * start(spec) takes the same spec as the local runner; a `passageId` re-runs an existing passage.
 */
export function createSfnRunner({ jobs, s3, sfn, bucket, stateMachineArn, logger = console }) {
  async function start(spec) {
    const { title } = spec;
    const passageId = spec.passageId ?? randomUUID();
    const rawKey = `raw/${passageId}.json`;
    const recording = spec.recording ?? (spec.recordingId ? { key: recordingKey(spec.recordingId) } : null);
    const input = buildJobInput({
      passageId,
      title,
      content: spec.content ?? textToHtml(spec.text),
      source: spec.source ?? "generated",
      language: spec.language,
      settings: spec.settings,
      pronunciations: spec.pronunciations,
      recording,
      humanPassageId: spec.humanPassageId,
    });
    const job = await jobs.create(title, { humanPassageId: input.humanPassageId });
    try {
      await s3.send(new PutObjectCommand({ Bucket: bucket, Key: rawKey, ContentType: "application/json", Body: JSON.stringify(input) }));
      await sfn.send(
        new StartExecutionCommand({
          stateMachineArn,
          name: job.id,
          input: JSON.stringify({ jobId: job.id, passageId, title, rawKey, humanPassageId: input.humanPassageId }),
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
