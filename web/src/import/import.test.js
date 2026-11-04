import { test } from "node:test";
import assert from "node:assert/strict";
import { strToU8, zipSync } from "fflate";
import { docxTextFromXml, extractDocxText } from "./docx.js";
import { pagesToText, pageLines } from "./pdfText.js";
import { ImportError, importFile, kindOf } from "./index.js";

const P = (runs) => `<w:p><w:r>${runs}</w:r></w:p>`;
const T = (s) => `<w:t xml:space="preserve">${s}</w:t>`;
const docx = (body, extra = {}) => zipSync({ "[Content_Types].xml": strToU8("<x/>"), "word/document.xml": strToU8(`<?xml version="1.0"?><w:document><w:body>${body}</w:body></w:document>`), ...extra });

test("a Word document becomes paragraphs of plain text", () => {
  const xml = `<w:body>${P(T("Chapter One"))}${P(T("It was a "))}${P(T("dark &amp; stormy night.") + "<w:tab/>" + T("The end."))}</w:body>`;
  assert.equal(docxTextFromXml(xml), "Chapter One\n\nIt was a\n\ndark & stormy night. The end.");
});

test("one paragraph made of several runs is joined, soft line breaks are kept, and deleted tracked changes are dropped", () => {
  const xml = `<w:p><w:r>${T("Hello ")}</w:r><w:r>${T("world")}</w:r><w:r><w:br/></w:r><w:r>${T("Second line")}</w:r><w:del><w:r><w:delText>gone</w:delText></w:r></w:del></w:p>`;
  assert.equal(docxTextFromXml(xml), "Hello world\nSecond line");
});

test("numeric character references are decoded and a bad one is dropped", () => {
  assert.equal(docxTextFromXml(P(T("caf&#233; &#x1F600; &#0;"))), "café 😀");
});

test("a real .docx file (a zip) is read", () => {
  const bytes = docx(P(T("Hola, ¿cómo estás?")));
  assert.equal(extractDocxText(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)), "Hola, ¿cómo estás?");
});

test("a file that is not a Word document, an empty one and an oversized one are refused with a message a person can act on", () => {
  const junk = new Uint8Array([1, 2, 3, 4, 5]).buffer;
  assert.throws(() => extractDocxText(junk), (e) => e instanceof ImportError && /does not look like a Word/.test(e.message));
  const noDoc = zipSync({ "a.txt": strToU8("x") });
  assert.throws(() => extractDocxText(noDoc.buffer.slice(noDoc.byteOffset, noDoc.byteOffset + noDoc.byteLength)), (e) => e instanceof ImportError && /could not find any text/.test(e.message));
  const empty = docx("<w:p></w:p>");
  assert.throws(() => extractDocxText(empty.buffer.slice(empty.byteOffset, empty.byteOffset + empty.byteLength)), /no text/);
  assert.throws(() => extractDocxText(new ArrayBuffer(16 * 1024 * 1024)), /larger than 15 MB/);
});

test("only word/document.xml is ever read: other zip entries, even huge ones, are never inflated", () => {
  const big = strToU8("a".repeat(2_000_000));
  const bytes = docx(P(T("Just this.")), { "word/media/huge.bin": big, "word/footnotes.xml": strToU8(`<w:p>${T("Footnote text")}</w:p>`) });
  assert.equal(extractDocxText(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)), "Just this.");
});

// ---- PDF text ------------------------------------------------------------------------------------------------------------------------
const item = (str, x, y, { w = str.length * 5, h = 10, eol = false } = {}) => ({ str, x, y, w, h, eol });

test("pieces on one baseline become one line, with a space only where there is a gap", () => {
  const lines = pageLines([item("Hel", 0, 700), item("lo", 15, 700), item("world", 40, 700, { eol: true })]);
  assert.deepEqual(lines.map((l) => l.text), ["Hello world"]);
});

test("reading order is the order given, so two columns do not interleave", () => {
  const left = [item("Left column first line", 50, 700, { eol: true }), item("Left column second line", 50, 686, { eol: true })];
  const right = [item("Right column first line", 320, 700, { eol: true }), item("Right column second line", 320, 686, { eol: true })];
  const text = pagesToText([{ items: [...left, ...right], height: 800 }]);
  assert.equal(text, "Left column first line\nLeft column second line\nRight column first line\nRight column second line");
});

test("page numbers and headers or footers that repeat on most pages are removed; page content is kept", () => {
  const page = (n) => ({
    height: 800,
    items: [item("The Great Story", 200, 780, { eol: true }), item(`Body text of page ${n} goes here.`, 50, 400, { eol: true }), item(String(n), 300, 20, { eol: true })],
  });
  const text = pagesToText([page(1), page(2), page(3), page(4)]);
  assert.ok(!text.includes("The Great Story") && !/^\d$/m.test(text));
  assert.ok(text.includes("Body text of page 1 goes here.") && text.includes("Body text of page 4 goes here."));
});

test("a bigger vertical gap marks a paragraph break", () => {
  const items = [item("First paragraph line one", 50, 700, { eol: true }), item("First paragraph line two", 50, 686, { eol: true }), item("Second paragraph starts here", 50, 650, { eol: true }), item("and continues", 50, 636, { eol: true })];
  assert.equal(pagesToText([{ items, height: 800 }]), "First paragraph line one\nFirst paragraph line two\n\nSecond paragraph starts here\nand continues");
});

test("a real page number inside the body text is not mistaken for furniture", () => {
  const items = [item("There were 12", 50, 400, { eol: true }), item("12", 50, 386, { eol: true })];
  assert.ok(pagesToText([{ items, height: 800 }]).includes("12"));
});

test("file kinds are recognised by extension and anything else is refused", async () => {
  assert.equal(kindOf({ name: "Story.DOCX" }), "docx");
  assert.equal(kindOf({ name: "a.pdf" }), "pdf");
  assert.equal(kindOf({ name: "a.exe" }), null);
  await assert.rejects(() => importFile({ name: "a.exe", size: 1 }), /cannot be added/);
});

test("a plain text file is read as it is and its title comes from the file name", async () => {
  const out = await importFile({ name: "My Story.txt", size: 20, text: async () => "Once upon a time." });
  assert.deepEqual(out, { title: "My Story", text: "Once upon a time." });
});


test("a Word file with one paragraph per printed line is rejoined; real paragraph breaks and headings stay", () => {
  const line = (s) => P(T(s));
  const xml = line("The Rabbit Hole") + line("Alice was beginning to get very tired of sitting by her sister on the") + line("bank, and of having nothing to do: once or twice she had peeped.") + line("Second paragraph starts here with enough words to be a long line of text") + line("and ends here.");
  assert.equal(docxTextFromXml(xml), "The Rabbit Hole\n\nAlice was beginning to get very tired of sitting by her sister on the\nbank, and of having nothing to do: once or twice she had peeped.\n\nSecond paragraph starts here with enough words to be a long line of text\nand ends here.");
});
