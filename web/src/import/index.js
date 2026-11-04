// One entry point for every kind of file a teacher can add. Everything is read in the browser; the text then goes into the editable box so it can be checked before audio is made.
import { titleFromFilename } from "../files.js";
import { ImportError } from "./importError.js";

export { ImportError };
export const TEXT_FILE_MAX_BYTES = 100 * 1024;
export const ACCEPT = ".txt,.md,.docx,.pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf";
const extensionOf = (name) => (String(name).match(/\.([^.]+)$/)?.[1] ?? "").toLowerCase();

export function kindOf(file) {
  const ext = extensionOf(file?.name);
  return ["txt", "md", "docx", "pdf"].includes(ext) ? ext : null;
}

/** {title, text} from a .txt, .md, .docx or .pdf file. Throws ImportError (a message for the teacher) when it cannot. */
export async function importFile(file) {
  const kind = kindOf(file);
  if (!kind) throw new ImportError("That kind of file cannot be added. Choose a .txt, .md, .docx or .pdf file, or paste the text into the box.");
  let text;
  if (kind === "docx") {
    const { extractDocxText } = await import("./docx.js");
    text = extractDocxText(await file.arrayBuffer());
  } else if (kind === "pdf") {
    const { extractPdfText } = await import("./pdf.js");
    text = await extractPdfText(await file.arrayBuffer());
  } else {
    if (file.size > TEXT_FILE_MAX_BYTES * 4) throw new ImportError("That text file is larger than 400 KB. Copy the part you need and paste it into the box instead.");
    text = await file.text();
  }
  return { title: titleFromFilename(file.name), text };
}
