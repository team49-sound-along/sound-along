import { test } from "node:test";
import assert from "node:assert/strict";
import { formatBytes, titleFromFilename, validateRecording, validateTextFile } from "./files.js";

test("title comes from the filename without extension", () => {
  assert.equal(titleFromFilename("The Gaieties.v2.md"), "The Gaieties.v2");
  assert.equal(titleFromFilename("noext"), "noext");
  assert.equal(titleFromFilename("x".repeat(200) + ".txt").length, 120);
});
test("text file accepts .txt/.md within 100 KB, .docx within 15 MB and .pdf within 25 MB", () => {
  assert.equal(validateTextFile({ name: "a.TXT", size: 10 }).ok, true);
  assert.equal(validateTextFile({ name: "a.md", size: 102400 }).ok, true);
  assert.match(validateTextFile({ name: "a.md", size: 102401 }).error, /100 KB/);
  assert.equal(validateTextFile({ name: "a.docx", size: 15 * 1024 * 1024 }).ok, true);
  assert.match(validateTextFile({ name: "a.docx", size: 15 * 1024 * 1024 + 1 }).error, /15 MB/);
  assert.equal(validateTextFile({ name: "a.pdf", size: 25 * 1024 * 1024 }).ok, true);
  assert.match(validateTextFile({ name: "a.pdf", size: 26 * 1024 * 1024 }).error, /25 MB/);
  assert.match(validateTextFile({ name: "a.exe", size: 10 }).error, /\.txt, \.md, \.docx or \.pdf/);
  assert.equal(validateTextFile(null).ok, false);
});
test("recording validates type, size, name", () => {
  assert.deepEqual(validateRecording({ name: "a.mp3", type: "audio/mpeg", size: 5 }), { ok: true, contentType: "audio/mpeg" });
  assert.equal(validateRecording({ name: "a.m4a", type: "", size: 5 }).contentType, "audio/x-m4a");
  assert.equal(validateRecording({ name: "a.ogg", type: "audio/ogg", size: 5 }).ok, false);
  assert.equal(validateRecording({ name: "a.wav", type: "audio/wav", size: 26_214_401 }).ok, false);
  assert.equal(validateRecording({ name: "a.wav", type: "audio/wav", size: 26_214_400 }).ok, true);
  assert.equal(validateRecording({ name: "a.wav", type: "audio/wav", size: 0 }).ok, false);
  assert.equal(validateRecording({ name: "a".repeat(120) + ".wav", type: "audio/wav", size: 5 }).ok, false);
});
test("formatBytes", () => {
  assert.equal(formatBytes(2048), "2 KB");
  assert.equal(formatBytes(1572864), "1.5 MB");
});
