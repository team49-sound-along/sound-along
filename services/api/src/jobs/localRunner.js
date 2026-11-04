import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createLocalRecordings } from "../recordings/localRecordings.js";
import { textToHtml } from "../validate.js";
import { buildJobInput } from "./jobInput.js";

const STEPS = new Set(["parse", "synthesize", "align", "publish"]);
const TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Runs the real Python pipeline (services/synth/run_local.py) as a child process and mirrors its progress
 * into the job store. In AWS this is replaced by a Step Functions state machine with the same four steps.
 *
 * start(spec): { title, text | content, source?, passageId?, settings, pronunciations, recordingId | recording, humanPassageId }
 * A `passageId` re-runs an existing passage (regenerate); otherwise a new one is created.
 */
export function createLocalRunner({ jobs, dataDir, python, script, logger = console }) {
  const recordings = createLocalRecordings({ dataDir });

  async function start(spec) {
    const { title } = spec;
    const passageId = spec.passageId ?? randomUUID();
    const recording = spec.recording ?? (spec.recordingId ? recordings.ref(spec.recordingId) : null);
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
    const rawDir = path.join(dataDir, "raw");
    await mkdir(rawDir, { recursive: true });
    const rawFile = path.join(rawDir, `${passageId}.json`);
    await writeFile(rawFile, JSON.stringify(input));

    const child = spawn(python, [script, rawFile, dataDir], { stdio: ["ignore", "pipe", "pipe"] });
    jobs.update(job.id, { status: "running", passageId });

    let buffer = "";
    let stderrTail = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), TIMEOUT_MS);

    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) handleLine(job.id, line);
    });
    child.stderr.on("data", (chunk) => {
      stderrTail = (stderrTail + chunk.toString()).slice(-2000);
    });
    child.on("error", (err) => finishFailed(job.id, "We could not start the audio generator. Please try again in a moment."));
    child.on("close", (code) => {
      clearTimeout(timer);
      if (buffer) handleLine(job.id, buffer);
      const current = jobs.get(job.id);
      if (current && current.status === "running") {
        logger.error("generation failed", { jobId: job.id, code, stderr: stderrTail.split("\n").slice(-3).join(" | ") });
        finishFailed(job.id, "We could not generate audio for this text. Try shorter text or remove unusual symbols.");
      }
    });
    return job;
  }

  function handleLine(jobId, line) {
    if (!line.trim()) return;
    let message;
    try {
      message = JSON.parse(line);
    } catch {
      return; // library chatter on stdout is ignored
    }
    if (message.step && STEPS.has(message.step)) jobs.update(jobId, { step: message.step });
    if (message.result) {
      jobs.update(jobId, { status: "done", step: "done", metrics: message.result, finishedAt: new Date().toISOString() });
    }
  }

  function finishFailed(jobId, error) {
    jobs.update(jobId, { status: "failed", error, finishedAt: new Date().toISOString() });
  }

  return { start };
}
