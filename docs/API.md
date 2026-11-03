# Sound Along API contract (v1)

Base: same origin. `/api/*` is the Express API, `/data/*` is static (S3 via CloudFront in AWS; a local folder in dev).
Every `/api` response uses one envelope:

```json
{ "success": true, "data": <payload>, "error": null, "meta": { } }
{ "success": false, "data": null, "error": "Human-readable message", "meta": { } }
```

## Static files (`/data/…`)
- `/data/{id}.timing.json`
  `{ id, title, engine, voice, duration_ms, metrics, vocab: { [senseId]: { word, definition, partOfSpeech?, examples?: string[], spanish?: string[] } }, pairId?: string, words: [ { i, text, start_ms, end_ms, sentence, paragraph, aligned, vocabId? } ] }`
  `metrics`: `{ characters, words, audioSeconds, generateSeconds, realTimeFactor, unalignedWords, pollyNeuralUsd, pollyStandardUsd, estimatedLambdaUsd, estimateBasis }`
- `/data/{id}.mp3` constant-bitrate 64 kbps mono (supports HTTP Range).

## Endpoints
| Method and path | Body | `data` |
|---|---|---|
| `GET /api/health` | | `{ status: "ok", generation: { enabled: boolean } }` |
| `GET /api/passages` | | `Passage[]` |
| `GET /api/classes` | | `Class[]` |
| `GET /api/assignments` | | `Assignment[]` (newest first) |
| `POST /api/assignments` | `{ passageId, classId, soundAlong: boolean, dueDate?: "YYYY-MM-DD" }` | `Assignment` (201) |
| `PATCH /api/assignments/:id` | `{ soundAlong: boolean }` | `Assignment` |
| `DELETE /api/assignments/:id` | | `{ id }` |
| `POST /api/generate` | `{ title: string (1-120), text: string (20-12000 chars) }` | `{ jobId }` (202). 429 when rate limited, 503 when generation is disabled |
| `GET /api/jobs/:id` | | `Job` |
| `POST /api/events` | `{ passageId, type: "play" \| "word_tap" \| "complete", classId? }` | `{ recorded: true }` |
| `GET /api/insights` | | `Insights` |

### Types
```ts
Passage    { id, title, words: number, durationMs: number, engine: "kokoro" | "polly" | "human" | string, voice: string, createdAt: string (ISO), source: "sample" | "generated", vocabCount: number, pairId: string | null }
           // pairId links the AI-voice and human-narrated variants of one text; the UI shows them as one card with a voice toggle
Class      { id, name, grade: string, students: number }                    // synthetic seed data
Assignment { id, passageId, passageTitle, classId, className, soundAlong: boolean, dueDate: string | null, createdAt: string }
Job        { id, title, status: "queued" | "running" | "done" | "failed", step: "parse" | "synthesize" | "align" | "publish" | "done",
             passageId: string | null, error: string | null, metrics: object | null, startedAt: string, finishedAt: string | null }
Insights   { catalog: { passages, words, characters, audioMinutes },
             quality: { alignedPercent: number,   // share of words the engine tokens mapped onto displayed words; NOT a sync measure
                        unalignedWords: number,
                        timingAgreement: { wordsChecked, wer, medianErrorMs, p95ErrorMs, within100ms, within250ms, method, generatedAt } | null,  // independent Whisper check, from data/quality-report.json
                        naturalness: { method, scores: { [label]: { meanMos, p10Mos, windows } } } | null },
             speed: { avgRealTimeFactor: number },
             cost: { pollyNeuralUsd, pollyStandardUsd, estimatedLambdaUsd, projectedCatalog: { characters: 20000000, pollyNeuralUsd, pollyStandardUsd, estimatedLambdaUsd }, basis: string },
             adoption: { plays: number, wordTaps: number, completions: number, assignmentsWithSoundAlong: number, assignmentsTotal: number } }
```

## Static files for the web client
Every `POST`/`PATCH` with a body must send `x-amz-content-sha256` (hex SHA-256 of the exact body) when served through CloudFront with Origin Access Control; the web client does this for all requests with a body.

## Behaviour notes
- Job `step` advances parse → synthesize → align → publish → done. `align` is the timing-verification step; poll `GET /api/jobs/:id` about once per second.
- `PATCH`/`DELETE` on unknown ids return 404 with the envelope.
- Validation errors return 400 with a message the UI can show verbatim.
