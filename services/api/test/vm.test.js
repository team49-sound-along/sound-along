import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { describe, test } from "node:test";
import { createAwsApp } from "../src/aws/awsApp.js";
import { assertEnv, createStreamLogger, installGracefulShutdown, parsePort, startVmServer } from "../src/aws/vmServer.js";

const ENV = { BUCKET: "B", TABLE_NAME: "T", GENERATION_ENABLED: "false", PORT: "0" };
const noClient = () => ({ calls: [], async send(c) { this.calls.push(c); return {}; } });
const clients = () => ({ ddb: noClient(), s3: noClient(), sfn: noClient() });
const sink = () => ({ out: "", write(s) { this.out += s; return true; } });
const fakeProc = () => Object.assign(new EventEmitter(), { exits: [], exit(code) { this.exits.push(code); } });

const stop = (server) => { server.close(); server.closeAllConnections?.(); };
const listening = (server) => new Promise((resolve) => (server.listening ? resolve() : server.once("listening", resolve)));

describe("parsePort / assertEnv", () => {
  test("defaults to 8080 and rejects bad values", () => {
    assert.equal(parsePort(undefined), 8080);
    assert.equal(parsePort("9000"), 9000);
    for (const bad of ["abc", "-1", "70000", "80.5"]) assert.throws(() => parsePort(bad), /Invalid PORT/);
  });
  test("names the missing variables", () => {
    assert.throws(() => assertEnv({ BUCKET: "B" }), /TABLE_NAME/);
    assert.doesNotThrow(() => assertEnv(ENV));
  });
});

describe("createAwsApp", () => {
  test("trusts one proxy hop by default and TRUSTED_PROXY_HOPS when set", () => {
    assert.equal(createAwsApp(ENV, clients()).get("trust proxy"), 1);
    assert.equal(createAwsApp({ ...ENV, TRUSTED_PROXY_HOPS: "2" }, clients()).get("trust proxy"), 2);
  });
});

describe("startVmServer", () => {
  test("serves /api/health without any AWS call, binds all interfaces, and logs to the streams", async () => {
    const c = clients();
    const stdout = sink();
    const proc = fakeProc();
    const { server } = startVmServer({ env: ENV, clients: c, stdout, stderr: sink(), proc });
    try {
      await listening(server);
      assert.equal(server.address().address, "0.0.0.0");
      const res = await fetch(`http://127.0.0.1:${server.address().port}/api/health`);
      assert.equal(res.status, 200);
      assert.deepEqual(await res.json(), { success: true, data: { status: "ok", generation: { enabled: false } }, error: null, meta: {} });
      assert.deepEqual([c.ddb.calls.length, c.s3.calls.length, c.sfn.calls.length], [0, 0, 0]);
      assert.match(stdout.out, /"msg":"listening"/);
      assert.equal(server.keepAliveTimeout, 65_000);
    } finally {
      stop(server);
    }
  });

  test("honours PORT", async () => {
    const { server } = startVmServer({ env: { ...ENV, PORT: "0" }, clients: clients(), stdout: sink(), stderr: sink(), proc: fakeProc() });
    try {
      await listening(server);
      assert.ok(server.address().port > 0);
    } finally {
      stop(server);
    }
  });

  test("refuses to start without BUCKET and TABLE_NAME", () => {
    assert.throws(() => startVmServer({ env: {}, clients: clients() }), /BUCKET, TABLE_NAME/);
  });
});

describe("installGracefulShutdown", () => {
  test("SIGTERM closes the server then exits 0, once", () => {
    const proc = fakeProc();
    let closes = 0;
    let done;
    const server = { close(cb) { closes += 1; done = cb; }, closeIdleConnections() {} };
    installGracefulShutdown({ server, proc, logger: createStreamLogger(sink(), sink()) });
    proc.emit("SIGTERM");
    proc.emit("SIGTERM");
    assert.equal(closes, 1);
    assert.deepEqual(proc.exits, []);
    done();
    assert.deepEqual(proc.exits, [0]);
  });

  test("forces exit 1 when connections do not drain in time", async () => {
    const proc = fakeProc();
    installGracefulShutdown({ server: { close() {} }, proc, logger: createStreamLogger(sink(), sink()), graceMs: 5 });
    proc.emit("SIGTERM");
    await new Promise((r) => setTimeout(r, 30));
    assert.deepEqual(proc.exits, [1]);
  });

  test("a real server shuts down on SIGTERM", async () => {
    const proc = fakeProc();
    const { server } = startVmServer({ env: ENV, clients: clients(), stdout: sink(), stderr: sink(), proc });
    await listening(server);
    const exited = new Promise((r) => { proc.exit = (code) => r(code); });
    proc.emit("SIGTERM");
    assert.equal(await exited, 0);
    server.closeAllConnections?.();
    assert.equal(server.listening, false);
  });
});
