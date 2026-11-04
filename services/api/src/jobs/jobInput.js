/** The generator's whole input (docs/API.md, "Job input file"). Pure: returns a new object. */
export function buildJobInput({ passageId, title, content, source, language = "en", settings, pronunciations, recording, humanPassageId, series = null }) {
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
    ...(series ? { series } : {}), // { id, index, total, title, partIds }: this passage is one part of a longer document
  };
}
