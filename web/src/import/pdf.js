// Text from a PDF, in the browser. pdf.js is loaded only when a PDF is chosen. It runs with eval turned off (older versions could be made to run
// code from a crafted PDF: CVE-2024-4367) and with scripting, forms and fonts disabled: only the text is wanted. Nothing is uploaded.
import { ImportError } from "./importError.js";
import { pagesToText } from "./pdfText.js";

export const PDF_MAX_BYTES = 25 * 1024 * 1024;
const MAX_PAGES = 150;

export async function extractPdfText(buffer) {
  if (buffer.byteLength > PDF_MAX_BYTES) throw new ImportError("That PDF is larger than 25 MB. Copy the text you need and paste it into the box instead.");
  const pdfjs = await import("pdfjs-dist/build/pdf.min.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  const task = pdfjs.getDocument({
    data: new Uint8Array(buffer),
    isEvalSupported: false,
    enableXfa: false,
    disableFontFace: true,
    useSystemFonts: false,
    stopAtErrors: false,
  });
  try {
    const doc = await task.promise;
    if (doc.numPages > MAX_PAGES) throw new ImportError(`That PDF has ${doc.numPages} pages. Documents up to ${MAX_PAGES} pages can be added; split it or paste the part you need.`);
    const pages = [];
    for (let n = 1; n <= doc.numPages; n += 1) {
      const page = await doc.getPage(n);
      const height = page.getViewport({ scale: 1 }).height;
      const content = await page.getTextContent();
      pages.push({
        height,
        items: content.items
          .filter((i) => typeof i.str === "string")
          .map((i) => ({ str: i.str, x: i.transform[4], y: i.transform[5], w: i.width, h: i.height || Math.abs(i.transform[3]), eol: Boolean(i.hasEOL) })),
      });
    }
    const text = pagesToText(pages);
    if (text.replace(/\s/g, "").length < 20 * Math.max(1, Math.min(doc.numPages, 3))) {
      throw new ImportError("That PDF has no text we can select (it may be a scan or a photo). Type the text, or copy it from another copy of the document.");
    }
    return text;
  } catch (err) {
    if (err instanceof ImportError) throw err;
    if (err?.name === "PasswordException") throw new ImportError("That PDF is password protected. Remove the password, or paste the text instead.");
    throw new ImportError("That PDF could not be read. Paste the text into the box instead.");
  } finally {
    task.destroy?.();
  }
}
