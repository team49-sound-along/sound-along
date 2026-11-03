/** The generator's whole input (docs/API.md, "Job input file"). Pure: returns a new object. */
export function buildJobInput({ passageId, title, content, source, language = "en", settings, pronunciations, recording, humanPassageId }) {
  return {
    uuid: passageId,
    title,
    content,
    source,
    language: language === "es" ? "es" : "en",
    settings,
    pronunciations,
    recording: recording ?? null,
    humanPassageId: recording ? (humanPassageId ?? null) : null,
    qualityCheck: true,
  };
}
