import { createAwsApp, createAwsClients } from "./awsApp.js";

const DEFAULT_PORT = 8080;
const SHUTDOWN_GRACE_MS = 10_000;
// CloudFront keeps origin connections idle for up to 5 s by default (60 s max); Node must outlast that or
// CloudFront occasionally reuses a socket Node just closed and returns 502.
const KEEP_ALIVE_MS = 65_000;
const REQUIRED_ENV = ["BUCKET", "TABLE_NAME"];

/** Logger with the shape createApp expects, writing to the given streams instead of console. */
export function createStreamLogger(stdout, stderr) {
  const line = (stream, level) => (msg, meta) =>
    stream.write(`${JSON.stringify({ level, msg, ...(meta ? { meta } : {}) })}\n`);
  return { info: line(stdout, "info"), warn: line(stderr, "warn"), error: line(stderr, "error") };
}

export function parsePort(value) {
  if (value === undefined || value === "") return DEFAULT_PORT;
  const port = Number(value);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error(`Invalid PORT "${value}": expected 0-65535.`);
  return port;
}

export function assertEnv(env) {
  const missing = REQUIRED_ENV.filter((name) => !env[name]);
  if (missing.length) throw new Error(`Missing required environment: ${missing.join(", ")}.`);
}

/** Close the server on SIGTERM (systemd stop), finish in-flight requests, then exit 0. Force exit after the grace period. */
export function installGracefulShutdown({ server, proc, logger, graceMs = SHUTDOWN_GRACE_MS }) {
  let closing = false;
  proc.on("SIGTERM", () => {
    if (closing) return;
    closing = true;
    logger.info("SIGTERM received, shutting down");
    const timer = setTimeout(() => {
      logger.error("shutdown timed out, forcing exit");
      proc.exit(1);
    }, graceMs);
    timer.unref?.();
    server.close((err) => {
      clearTimeout(timer);
      proc.exit(err ? 1 : 0);
    });
    server.closeIdleConnections?.();
  });
}

/**
 * Start the CMS API on a VM. Listens on 0.0.0.0:PORT (default 8080); the security group only admits CloudFront.
 * Returns { app, server, logger }. Everything environmental is injectable for tests.
 */
export function startVmServer({ env = process.env, clients, stdout = process.stdout, stderr = process.stderr, proc = process } = {}) {
  assertEnv(env);
  const port = parsePort(env.PORT);
  const logger = createStreamLogger(stdout, stderr);
  const app = createAwsApp(env, clients ?? createAwsClients(), logger);
  const server = app.listen(port, "0.0.0.0", () => logger.info("listening", { port }));
  server.keepAliveTimeout = KEEP_ALIVE_MS;
  server.headersTimeout = KEEP_ALIVE_MS + 1000;
  installGracefulShutdown({ server, proc, logger });
  return { app, server, logger };
}
