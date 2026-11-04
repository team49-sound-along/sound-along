import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createLocalRecordings } from "../recordings/localRecordings.js";
import { textToHtml } from "../validate.js";
import { buildJobInput } from "./jobInput.js";

const STEPS = new Set(["parse", "synthesize", "align", "publish", "translate"]);
const TIMEOUT_MS = 20 * 60 * 1000; // narration, then the translation and its narration, for one run (a long document gets this much per chunk, up to MAX_TIMEOUT_MS)
const MAX_TIMEOUT_MS = 6 * 60 * 60 * 1000;

/**
 * Runs the real Python pipeline (services/synth/run_local.py) as a child process and mirrors its progress
 * into the job store. In AWS this is replaced by a Step Functions state machine with the same four steps.
 *
 * start(spec): { title, text | content, source?, passageId?, settings, pronunciations, recordingId | recording, humanPassageId, chunks? | chunkHtml? }
 * A long document arrives with `chunks` (text pieces, or `chunkHtml` when regenerating): they are narrated one after another inside ONE run and joined into ONE passage.
 * A `passageId` re-runs an existing passage (regenerate); otherwise a new one is created.
 */
export function createLocalRunner({ jobs, dataDir, python, script, logger = console }) {
  const recordings = createLocalRecordings({ dataDir });

  /** Creates the job and writes its input file. Returns { job, run } where run() does the work and resolves when it ends (it never rejects). */
  async function prepare(spec) {
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
      chunks: spec.chunkHtml ?? spec.chunks?.map((piece) => textToHtml(piece)),
    });
    const job = await jobs.create(title, { humanPassageId: input.humanPassageId, chunks: input.chunks?.length ?? 0 });
    const rawDir = path.join(dataDir, "raw");
    await mkdir(rawDir, { recursive: true });
    const rawFile = path.join(rawDir, `${passageId}.json`);
    await writeFile(rawFile, JSON.stringify(input));
    jobs.update(job.id, { passageId });
    return { job: { ...job, passageId }, run: () => execute(job, rawFile, passageId, input.chunks?.length ?? 0) };
  }

  function execute(job, rawFile, passageId, chunkCount = 0) {
    return new Promise((resolve) => {
    const child = spawn(python, [script, rawFile, dataDir], { stdio: ["ignore", "pipe", "pipe"] });
    jobs.update(job.id, { status: "running", passageId });

    let buffer = "";
    let stderrTail = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), Math.min(MAX_TIMEOUT_MS, TIMEOUT_MS * Math.max(1, chunkCount)));

    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) handleLine(job.id, line);
    });
    child.stderr.on("data", (chunk) => {
      stderrTail = (stderrTail + chunk.toString()).slice(-2000);
    });
    child.on("error", () => {
      finishFailed(job.id, "We could not start the audio generator. Please try again in a moment.");
      resolve();
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (buffer) handleLine(job.id, buffer);
      const current = jobs.get(job.id);
      if (current && current.status === "running") {
        logger.error("generation failed", { jobId: job.id, code, stderr: stderrTail.split("\n").slice(-3).join(" | ") });
        finishFailed(job.id, "We could not generate audio for this text. Try shorter text or remove unusual symbols.");
      }
      resolve();
    });
    });
  }

  async function start(spec) {
    const { job, run } = await prepare(spec);
    run();
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
    if (message.chunk) jobs.update(jobId, { step: "synthesize", chunksDone: message.chunk.done, chunksTotal: message.chunk.total });
    if (message.result) {
      jobs.update(jobId, { status: "done", step: "done", metrics: message.result, finishedAt: new Date().toISOString() });
    }
  }

  function finishFailed(jobId, error) {
    jobs.update(jobId, { status: "failed", error, finishedAt: new Date().toISOString() });
  }

  return { start };
}
