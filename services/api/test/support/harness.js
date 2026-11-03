import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createApp } from "../../src/app.js";
import { createFileCatalog } from "../../src/catalog.js";
import { createJobStore } from "../../src/jobs/jobStore.js";
import { createLocalSources } from "../../src/jobs/localSources.js";
import { createLocalRecordings } from "../../src/recordings/localRecordings.js";
import { createFileStore } from "../../src/stores/fileStore.js";

export const TEXT = "A short passage that is long enough to pass validation.";
export const quiet = { error() {}, warn() {}, info() {} };

/** A fully local app (file store, file catalog, local recordings and sources) on a temp folder, with a recording runner. */
export async function startLocalApp({ config = {}, runner, dir } = {}) {
  const dataDir = dir ?? (await mkdtemp(path.join(tmpdir(), "sa-v2-")));
  const jobs = createJobStore();
  const started = [];
  const recordings = createLocalRecordings({ dataDir });
  const app = createApp({
    store: createFileStore(path.join(dataDir, "state.json")),
    catalog: createFileCatalog(dataDir),
    jobs,
    recordings,
    sources: createLocalSources({ dataDir }),
    runner: runner ?? { start: async (spec) => { started.push(spec); return jobs.create(spec.title, { humanPassageId: spec.humanPassageId }); } },
    config: { dataDir, generationEnabled: true, maxConcurrentJobs: 1, generatePerMinute: 50, ...config },
    logger: quiet,
  });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (method, url, body) => {
    const res = await fetch(base + url, {
      method,
      headers: body === undefined ? {} : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* empty body */ }
    return { status: res.status, json, text, headers: res.headers };
  };
  return { dataDir, base, call, jobs, started, close: () => server.closeAllConnections?.() ?? server.close(), server };
}

/** Fake AWS client: records commands and answers with respond(command). */
export function fakeClient(respond = () => ({})) {
  const calls = [];
  return {
    calls,
    async send(command) {
      calls.push({ name: command.constructor.name, input: command.input });
      return respond(command, calls.length);
    },
  };
}
