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
 * A long document (spec.chunks as text, or spec.chunkHtml when regenerating) is still ONE job and ONE passage: its chunks get internal ids and their own inputs
 * (raw/{chunkId}.json), are narrated in a private work folder, and the state machine joins them into the passage at the end.
 */
export function createSfnRunner({ jobs, s3, sfn, bucket, stateMachineArn, logger = console }) {
  const put = (key, body) => s3.send(new PutObjectCommand({ Bucket: bucket, Key: key, ContentType: "application/json", Body: JSON.stringify(body) }));

  async function failJob(job, err) {
    logger.error("could not start generation", { jobId: job.id, message: err?.message });
    await jobs.update(job.id, { status: "failed", error: FRIENDLY_FAILURE, finishedAt: new Date().toISOString() });
    throw new HttpError(503, FRIENDLY_FAILURE);
  }

  async function execute(job, passageId, input, executionInput) {
    try {
      await sfn.send(new StartExecutionCommand({ stateMachineArn, name: job.id, input: JSON.stringify(executionInput) }));
    } catch (err) {
      await failJob(job, err);
    }
    return (await jobs.update(job.id, { passageId })) ?? { ...job, passageId };
  }

  /** Creates the job and writes the generator's input to S3. The state machine only ever receives keys (its state is limited to 256 KB). */
  async function start(spec) {
    const { title } = spec;
    const passageId = spec.passageId ?? randomUUID();
    const rawKey = `raw/${passageId}.json`;
    const recording = spec.recording ?? (spec.recordingId ? { key: recordingKey(spec.recordingId) } : null);
    const chunkHtml = spec.chunkHtml ?? spec.chunks?.map((piece) => textToHtml(piece));
    const common = { source: spec.source ?? "generated", language: spec.language, settings: spec.settings, pronunciations: spec.pronunciations };
    const input = buildJobInput({ passageId, title, content: spec.content ?? textToHtml(spec.text), ...common, recording, humanPassageId: spec.humanPassageId, chunks: chunkHtml });
    const job = await jobs.create(title, { humanPassageId: input.humanPassageId, chunks: chunkHtml?.length ?? 0 });
    const chunkIds = (chunkHtml ?? []).map(() => randomUUID());
    try {
      await put(rawKey, input);
      for (const [k, id] of chunkIds.entries()) await put(`raw/${id}.json`, buildJobInput({ passageId: id, title, content: chunkHtml[k], ...common }));
    } catch (err) {
      await failJob(job, err);
    }
    if (!chunkIds.length) {
      return execute(job, passageId, input, { parts: [{ jobId: job.id, passageId, title, rawKey, humanPassageId: input.humanPassageId }] });
    }
    const chunks = chunkIds.map((id) => ({ jobId: job.id, passageId: id, rawKey: `raw/${id}.json`, title, workFor: passageId }));
    return execute(job, passageId, input, { document: { jobId: job.id, passageId, title, rawKey, chunkIds, chunks } });
  }

  return { start };
}
