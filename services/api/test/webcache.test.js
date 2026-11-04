import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test, { after } from "node:test";
import { startLocalApp } from "./support/harness.js";

const webDist = await mkdtemp(path.join(tmpdir(), "sa-web-"));
await mkdir(path.join(webDist, "assets"));
await writeFile(path.join(webDist, "index.html"), "<!doctype html><title>x</title>");
await writeFile(path.join(webDist, "assets", "index-abc123.js"), "console.log(1)");
const ctx = await startLocalApp({ config: { webDist } });
after(() => ctx.close());

test("built files with a hash in their name are cached for a year, and the page itself is always checked for a newer build", async () => {
  const asset = await fetch(`${ctx.base}/assets/index-abc123.js`);
  assert.equal(asset.headers.get("cache-control"), "public, max-age=31536000, immutable");
  for (const url of ["/", "/index.html", "/some/deep/link"]) {
    const page = await fetch(ctx.base + url);
    assert.equal(page.status, 200);
    assert.equal(page.headers.get("cache-control"), "no-cache", url);
  }
});
