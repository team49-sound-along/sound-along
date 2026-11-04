// Text from a Word (.docx) file, in the browser. A .docx is a zip file; the text is in word/document.xml. Only that one entry is ever read,
// and only if its declared size is reasonable, so a zip bomb cannot exhaust memory. Nothing is uploaded: the file never leaves the computer.
import { unzipSync } from "fflate";
import { ImportError } from "./importError.js";

export const DOCX_MAX_BYTES = 15 * 1024 * 1024;
const XML_MAX_BYTES = 30 * 1024 * 1024;

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const decode = (s) =>
  s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
    if (e[0] === "#") {
      const code = e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
    }
    return ENTITIES[e.toLowerCase()] ?? m;
  });

/** Paragraphs of word/document.xml as plain text, separated by blank lines. Deleted tracked changes are skipped; tabs become spaces. */
export function docxTextFromXml(xml) {
  const body = xml.replace(/<w:del\b[\s\S]*?<\/w:del>/g, "").replace(/<w:(?:instrText|delText)\b[\s\S]*?<\/w:(?:instrText|delText)>/g, "");
  const paragraphs = [];
  for (const [, inner] of body.matchAll(/<w:p\b[^>]*>([\s\S]*?)<\/w:p>/g)) {
    let text = "";
    for (const m of inner.matchAll(/<w:t(?:\s[^>]*)?>([^<]*)<\/w:t>|<w:tab\s*\/>|<w:br\s*\/>|<w:cr\s*\/>/g)) {
      if (m[0].startsWith("<w:t>") || m[0].startsWith("<w:t ")) text += decode(m[1]);
      else text += m[0].startsWith("<w:tab") ? " " : "\n";
    }
    text = text.replace(/[ \t]+/g, " ").replace(/ ?\n ?/g, "\n").trim();
    if (text) paragraphs.push(text);
  }
  // Word files made by pasting from a PDF or an email store every printed line as its own paragraph. A paragraph that is long and does not end a
  // sentence is such a line, so it is joined to the next with a single line break (the server then joins it); a real paragraph break stays a blank line.
  return paragraphs.reduce((out, p, i) => {
    if (i === 0) return p;
    const previous = paragraphs[i - 1];
    const wrapped = previous.length >= 40 && !/[.!?\u2026:;"'\u201D\u2019\u00BB)\]]$/.test(previous);
    return out + (wrapped ? "\n" : "\n\n") + p;
  }, "");
}

/** Text of a .docx file given as an ArrayBuffer. Throws ImportError with a message a teacher can act on. */
export function extractDocxText(buffer) {
  if (buffer.byteLength > DOCX_MAX_BYTES) throw new ImportError("That Word file is larger than 15 MB. Copy the text you need and paste it into the box instead.");
  let files;
  try {
    files = unzipSync(new Uint8Array(buffer), { filter: (f) => f.name === "word/document.xml" && f.originalSize <= XML_MAX_BYTES });
  } catch {
    throw new ImportError("That does not look like a Word (.docx) file, or it is damaged. Paste the text into the box instead.");
  }
  const entry = files["word/document.xml"];
  if (!entry) throw new ImportError("We could not find any text in that Word file. Older .doc files are not supported: save it as .docx first, or paste the text.");
  const text = docxTextFromXml(new TextDecoder("utf-8").decode(entry));
  if (!text) throw new ImportError("That Word file has no text in it.");
  return text;
}
