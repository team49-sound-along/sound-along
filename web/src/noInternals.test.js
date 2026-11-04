// People using the app never see how it is built: no endpoints, no HTTP codes, no service or engine internals in anything they can read.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL(".", import.meta.url));
const files = (dir) => readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? (f === "assets" ? [] : files(join(dir, f))) : [join(dir, f)]));
// jobSteps.js is exempt: it holds the list of internal words it must HIDE from error messages (tested in jobSteps.test.js).
const sources = files(ROOT).filter((f) => /\.(vue|js)$/.test(f) && !/\.test\.js$/.test(f) && !f.endsWith("jobSteps.js"));

// Text a person can read: template text and string literals (not code, import paths or comments).
const withoutComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1").replace(/<!--[\s\S]*?-->/g, "");
const BANNED = [
  [/\b(GET|POST|PUT|PATCH|DELETE) \/api\b/, "an endpoint"],
  [/HTTP \$\{|\(HTTP \d|HTTP \d{3}/, "an HTTP status"],
  [/\b(on|by|from) this server\b/i, "'this server'"],
  [/\b(Lambda|DynamoDB|Step Functions|CloudFront|Whisper|Kokoro|Phonon)\b/, "an internal service or engine name"],
  [/job metrics from/i, "job metrics source"],
  [/not rated yet|Sign-in is simulated|Demo data|word-level timing|development computer/i, "an internal or prototype note"],
];

test("no screen shows an endpoint, an HTTP code or an internal service name", () => {
  const problems = [];
  for (const file of sources) {
    const text = withoutComments(readFileSync(file, "utf8"));
    for (const [pattern, what] of BANNED) {
      const m = text.match(pattern);
      if (m) problems.push(`${file.replace(ROOT, "")}: ${what}: ${m[0]}`);
    }
  }
  assert.deepEqual(problems, []);
});
