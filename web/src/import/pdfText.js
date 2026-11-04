// Turn the text pieces pdf.js reports for each page into readable paragraphs. Pure functions, no pdf.js needed, so they can be tested with plain data.
//
// A page is a list of items { str, x, y, w, h, eol }: the text, position (PDF units, y grows upward), width, font height and "ends a line".
// Reading order is the order pdf.js gives (the order the file was written in), which keeps two-column pages in column order; items are never re-sorted by y.

const PAGE_NUMBER = /^\s*(?:page\s+)?(?:\d{1,4}|[ivxlcdm]{1,7})(?:\s*(?:of|\/)\s*\d{1,4})?\s*$/i;
const NEW_LINE_FACTOR = 0.6; // a jump in y of more than this many font heights starts a new line
const GAP_SPACE_FACTOR = 0.18; // a horizontal gap of more than this many font heights between two pieces is a space
const PARAGRAPH_GAP_FACTOR = 1.55; // a vertical gap this many times the usual line spacing is a paragraph break
const MARGIN = 0.08; // the top and bottom 8% of a page is where headers and footers live

/** Lines of one page: { text, y, h }. */
export function pageLines(items) {
  const lines = [];
  let current = null;
  let last = null;
  for (const it of items) {
    const str = it.str ?? "";
    if (!str && !it.eol) continue;
    const h = it.h > 0 ? it.h : 10;
    const sameLine = current && Math.abs(it.y - current.y) <= NEW_LINE_FACTOR * Math.max(h, current.h);
    if (!sameLine) {
      current = { text: "", y: it.y, h, parts: 0 };
      lines.push(current);
      last = null;
    }
    if (last && str) {
      const gap = it.x - (last.x + last.w);
      const needsSpace = !/\s$/.test(current.text) && !/^\s/.test(str) && gap > GAP_SPACE_FACTOR * h;
      if (needsSpace) current.text += " ";
    }
    current.text += str;
    current.h = Math.max(current.h, h);
    if (str) last = it;
    if (it.eol) {
      current = null;
      last = null;
    }
  }
  return lines.map((l) => ({ text: l.text.replace(/[ \t]+/g, " ").trim(), y: l.y, h: l.h })).filter((l) => l.text);
}

const signature = (text) => text.toLowerCase().replace(/\d+/g, "#").replace(/\s+/g, " ").trim();

/** Page numbers, and headers or footers that repeat on at least half of the pages (digits ignored: "Chapter 1 | 12"), are dropped. */
function withoutFurniture(pages) {
  const counts = new Map();
  for (const { lines, height } of pages) {
    const seen = new Set();
    for (const l of lines) {
      if (height && (l.y > height * (1 - MARGIN) || l.y < height * MARGIN)) {
        const sig = signature(l.text);
        if (!seen.has(sig)) counts.set(sig, (counts.get(sig) ?? 0) + 1);
        seen.add(sig);
      }
    }
  }
  const repeated = new Set(pages.length >= 3 ? [...counts].filter(([, n]) => n >= Math.ceil(pages.length / 2)).map(([s]) => s) : []);
  return pages.map(({ lines, height }) =>
    lines.filter((l) => {
      const inMargin = height && (l.y > height * (1 - MARGIN) || l.y < height * MARGIN);
      if (PAGE_NUMBER.test(l.text) && (inMargin || !height)) return false;
      return !(inMargin && repeated.has(signature(l.text)));
    }),
  );
}

/** pages: [{ items, height }]. Returns text with a blank line between paragraphs and one line per printed line (the server joins wrapped lines). */
export function pagesToText(pages) {
  const prepared = pages.map((p) => ({ lines: pageLines(p.items), height: p.height }));
  const cleaned = withoutFurniture(prepared);
  const out = [];
  for (const lines of cleaned) {
    const gaps = [];
    for (let i = 1; i < lines.length; i += 1) {
      const d = lines[i - 1].y - lines[i].y;
      if (d > 0) gaps.push(d);
    }
    gaps.sort((a, b) => a - b);
    const usual = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0;
    lines.forEach((l, i) => {
      if (i > 0 && usual > 0 && lines[i - 1].y - l.y > PARAGRAPH_GAP_FACTOR * usual) out.push("");
      out.push(l.text);
    });
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
