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
  /** Creates the job and writes the generator's input to S3. The state machine only ever receives keys (its state is limited to 256 KB). */
  async function prepare(spec) {
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
      series: spec.series,
    });
    const job = await jobs.create(title, { humanPassageId: input.humanPassageId });
    try {
      await s3.send(new PutObjectCommand({ Bucket: bucket, Key: rawKey, ContentType: "application/json", Body: JSON.stringify(input) }));
    } catch (err) {
      await failJob(job, err);
    }
    return { job, passageId, part: { jobId: job.id, passageId, title, rawKey, humanPassageId: input.humanPassageId } };
  }

  async function failJob(job, err) {
    logger.error("could not start generation", { jobId: job.id, message: err?.message });
    await jobs.update(job.id, { status: "failed", error: FRIENDLY_FAILURE, finishedAt: new Date().toISOString() });
    throw new HttpError(503, FRIENDLY_FAILURE);
  }

  /** One Step Functions execution for the whole submission: {parts: [...]} (one entry for an ordinary passage). */
  async function execute(prepared, name) {
    try {
      await sfn.send(new StartExecutionCommand({ stateMachineArn, name, input: JSON.stringify({ parts: prepared.map((p) => p.part) }) }));
    } catch (err) {
      await Promise.all(prepared.map((p) => jobs.update(p.job.id, { status: "failed", error: FRIENDLY_FAILURE, finishedAt: new Date().toISOString() })));
      logger.error("could not start generation", { message: err?.message });
      throw new HttpError(503, FRIENDLY_FAILURE);
    }
    return Promise.all(prepared.map(async (p) => (await jobs.update(p.job.id, { passageId: p.passageId })) ?? { ...p.job, passageId: p.passageId }));
  }

  async function start(spec) {
    const prepared = await prepare(spec);
    const [job] = await execute([prepared], prepared.job.id);
    return job;
  }

  /** A long document: every part's job exists now, and the parts are generated one after another by one execution. */
  async function startSeries(specs) {
    const prepared = [];
    for (const spec of specs) prepared.push(await prepare(spec));
    return execute(prepared, specs[0].series.id);
  }

  return { start, startSeries };
}
