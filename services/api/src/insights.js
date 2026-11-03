// Aggregates the success metrics from real generation output. Nothing here is invented:
// when there is no data the values are null/0 and the UI shows a dash.
export const CATALOG_CHARACTERS = 20_000_000; // ReadWorks' stated catalog size (vision document)
const POLLY_NEURAL_PER_M = 16;
const POLLY_STANDARD_PER_M = 4;

const sum = (items, pick) => items.reduce((total, item) => total + (pick(item) ?? 0), 0);
const round = (value, places) => (value == null ? null : Number(value.toFixed(places)));

export function buildInsights({ timings, assignments, events, qualityReport = null, blindRating = null }) {
  // A human-narrated variant shares its text with the AI-voice passage, so it must not double-count
  // characters, cost or generation speed. Alignment quality still counts every variant.
  const generated = timings.filter((t) => t.engine !== "human");
  const humanNarrated = timings.length - generated.length;
  const allMetrics = timings.map((t) => t.metrics ?? {});
  const metrics = generated.map((t) => t.metrics ?? {});
  const characters = sum(metrics, (m) => m.characters);
  const words = sum(allMetrics, (m) => m.words);
  const unaligned = sum(allMetrics, (m) => m.unalignedWords);
  const audioSeconds = sum(metrics, (m) => m.audioSeconds);
  const generateSeconds = sum(metrics, (m) => m.generateSeconds);
  const lambdaUsd = sum(metrics, (m) => m.estimatedLambdaUsd);
  const lambdaPerChar = characters > 0 ? lambdaUsd / characters : null;
  const withSoundAlong = assignments.filter((a) => a.soundAlong).length;

  return {
    catalog: {
      passages: generated.length,
      humanNarrated,
      words: sum(metrics, (m) => m.words),
      characters,
      audioMinutes: round(sum(allMetrics, (m) => m.audioSeconds) / 60, 1),
    },
    quality: {
      // Share of words the engine's own tokens mapped onto the displayed words. It does NOT measure sync with audio;
      // timingAgreement (below) is the independent check.
      alignedPercent: words > 0 ? round(((words - unaligned) / words) * 100, 2) : null,
      unalignedWords: unaligned,
      timingAgreement: qualityReport?.asr?.pooled
        ? { ...qualityReport.asr.pooled, method: qualityReport.asr.method, generatedAt: qualityReport.generatedAt }
        : null,
      naturalness: qualityReport?.naturalness ?? null,
      blindRating,
    },
    speed: {
      avgRealTimeFactor: audioSeconds > 0 ? round(generateSeconds / audioSeconds, 3) : null,
    },
    cost: {
      pollyNeuralUsd: round((characters / 1e6) * POLLY_NEURAL_PER_M, 4),
      pollyStandardUsd: round((characters / 1e6) * POLLY_STANDARD_PER_M, 4),
      estimatedLambdaUsd: round(lambdaUsd, 4),
      projectedCatalog: {
        characters: CATALOG_CHARACTERS,
        pollyNeuralUsd: round((CATALOG_CHARACTERS / 1e6) * POLLY_NEURAL_PER_M, 2),
        pollyStandardUsd: round((CATALOG_CHARACTERS / 1e6) * POLLY_STANDARD_PER_M, 2),
        estimatedLambdaUsd: lambdaPerChar == null ? null : round(lambdaPerChar * CATALOG_CHARACTERS, 2),
      },
      basis: metrics.find((m) => m.estimateBasis)?.estimateBasis ?? "No generation data yet",
    },
    adoption: {
      plays: events.plays,
      wordTaps: events.wordTaps,
      completions: events.completions,
      assignmentsWithSoundAlong: withSoundAlong,
      assignmentsTotal: assignments.length,
    },
  };
}
