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

---

# v2: teacher content on demand, editable settings, pronunciation review

Everything a teacher or content editor does is stored data, not code. Settings and pronunciation fixes are read when a job starts and are snapshotted into the job's input file, so the generator needs no database access (see "Job input file").

## New and changed endpoints
| Method and path | Body | `data` |
|---|---|---|
| `GET /api/settings` | | `Settings` |
| `PUT /api/settings` | `{ voice, speed, mp3Kbps }` (partial allowed) | `Settings` |
| `GET /api/pronunciations` | | `Pronunciation[]` (sorted by word) |
| `PUT /api/pronunciations/:word` | `{ respelling }` | `Pronunciation` (201 new, 200 replaced) |
| `DELETE /api/pronunciations/:word` | | `{ word }` |
| `POST /api/recordings` | `{ filename, contentType, size }` | `{ recordingId, upload: { method: "PUT", url, headers } }` |
| `PUT <upload.url>` | raw audio bytes | 204. Locally `url` is `/api/recordings/{recordingId}/content`; on AWS it is a presigned S3 URL. The client always PUTs the file to `upload.url` with `upload.headers`. |
| `POST /api/generate` | `{ title, text, recordingId? }` | `{ jobId }` (202). With `recordingId` the job also aligns the uploaded human recording and publishes a human-narrated variant linked to the AI variant by `pairId`. |
| `GET /api/review` | | `ReviewItem[]`: passages that have pronunciation suspects not yet dismissed or fixed |
| `POST /api/review/dismiss` | `{ word }` | `{ word }`. Hides this suspect word everywhere. |
| `POST /api/passages/:id/regenerate` | | `{ jobId }` (202). Re-runs generation from the stored source text using the CURRENT settings and pronunciations. 404 if the passage has no stored source. |

### Types
```ts
Settings       { voice: string, speed: number, mp3Kbps: number,
                 voices: { id: string, label: string }[] }   // voices is read-only, from a config file
Pronunciation  { word: string, respelling: string, updatedAt: string }
ReviewItem     { passageId: string, title: string, source: "asr-check", suspects: { expected: string, heard: string }[] }
Job            // adds: humanPassageId: string | null
```

### Rules
- `voice` must be one of `voices[].id` (the Kokoro US/UK English voices in `services/api/config/voices.json`). `speed` is 0.7 to 1.2. `mp3Kbps` is an integer 24 to 128. Defaults: `af_heart`, `0.95`, `48`.
- `word`: lowercase letters, apostrophes and hyphens only, 1 to 40 characters (case-insensitive on input; stored lowercase). `respelling`: 1 to 60 characters; either plain letters, spaces and hyphens ("gay-uh-teez"), or phonemes wrapped in slashes ("/ɡˈAɪtˌiz/").
- Recording: `contentType` one of `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/mp4`, `audio/x-m4a`, `audio/webm`; `size` at most 25 MB (26,214,400 bytes); `filename` at most 120 characters. Reject others with 400 and a readable message.
- Text: the existing 20 to 12,000 character limits apply. A `.txt` or `.md` file is read in the browser and sent as `text`.
- All error responses use the same envelope as v1. Writes through CloudFront must send `x-amz-content-sha256` (the web client already does).

## Job input file (`raw/{passageId}.json`, local folder or S3)
Written by the API when a job starts. This is the generator's whole input.
```json
{ "uuid": "...", "title": "...", "content": "<p>...</p>", "source": "generated",
  "settings": { "voice": "af_heart", "speed": 0.95, "mp3Kbps": 48 },
  "pronunciations": { "gaieties": "gayetees" },
  "recording": { "path": "<local file>" } | { "key": "raw/<recordingId>.audio" } | null,
  "humanPassageId": "<uuid>" | null,
  "qualityCheck": true }
```
`humanPassageId` is the id the generator must use for the human-narrated variant (the API chooses it so the job can report it before the work finishes).

## Timing document additions
`review: { "source": "asr-check", "suspects": [ { "expected": "gaieties", "heard": "deities" } ] }` is written at generation when `qualityCheck` is true. Suspects exclude differences explained by British/American spelling. `settings` and `pronunciations` used for the run are recorded under `generatedWith`.

---

# v3: Spanish passages and the blind listening test

## Spanish
- `POST /api/generate` accepts `language: "en" | "es"` (default `"en"`). Spanish passages are spoken by a Kokoro Spanish voice; word timing comes from a multilingual speech-recognition pass because Kokoro gives no word timing for Spanish. The pipeline handles that; the API only passes the language through.
- `Settings` gains `voiceEs` (default `"ef_dora"`). `voice` must be an English voice and `voiceEs` a Spanish voice. Each entry of `Settings.voices` gains `lang: "en" | "es"`.
  `services/api/config/voices.json` therefore holds the four English voices graded B- or better (see `config/VOICES.md`) with `"lang": "en"` and three Spanish voices: `ef_dora` ("Dora (Spanish female, not graded)"), `em_alex` ("Alex (Spanish male, not graded)"), `em_santa` ("Santa (Spanish male, not graded)"), each with `"lang": "es"`.
- Job input file: add `"language": "en" | "es"`. `settings` still carries `voice`, `speed`, `mp3Kbps` and now `voiceEs`.
- `Passage` gains `language: "en" | "es"` (from the timing document's `language`, default `"en"`).
- Pronunciation fixes apply to English passages only (the UI says so).

## Blind listening test (the vision document's "blind listener rating" metric)
Clips are short anonymous excerpts (about 30 s) of the SAME text read by different narrators, loudness-matched and encoded identically, built by `scripts/build_samples.py`. The files are `data/ab/<token>.mp3` where `<token>` is 16 random hex characters, so a URL does not reveal which narrator it is. `data/ab/manifest.json` (never served) maps tokens to meaning:
```json
[ { "token": "9f3a1c0b5d7e2a46", "passageId": "<uuid>", "title": "Let's Meet a Park Caretaker", "kind": "ai" | "human" | "polly_current" } ]
```
On AWS the same files live in S3 under `data/ab/` and the manifest at `data/ab/manifest.json` (read by the API, never exposed through CloudFront).

| Method and path | Body | `data` |
|---|---|---|
| `GET /api/ratings/trial` | | `Trial` or `null` when there are no clips |
| `POST /api/ratings` | `{ trialId, aToken, bToken, preferred: "a" \| "b" \| "tie", ratingA: 1..5, ratingB: 1..5, raterId?: uuid }` | `{ recorded: true }` |
| `GET /api/ratings/summary` | | `RatingSummary` |
| `GET /data/ab/:token.mp3` | | the clip (local API route; CloudFront on AWS). Token must be 16 hex characters. |

```ts
Trial         { trialId: uuid, title: string, prompt: string, a: { token: string, url: string }, b: { token: string, url: string } }
              // a pair = the AI voice and one other narrator of the same passage, in random order; url is /data/ab/<token>.mp3
RatingSummary { raters: number, ratings: number,
                comparisons: { comparison: "ai vs human" | "ai vs polly_current", n: number, preferredAi: number, preferredOther: number, tie: number }[],
                meanRating: { ai: number | null, human: number | null, polly_current: number | null } }
```
Rules: tokens in POST must exist in the manifest and belong to the same passage with one `ai` clip; reject otherwise with a readable 400. Ratings are real data from real listeners; never seed fake ones. Rate-limit and kill-switch the write route like the other writes. `Insights.quality` gains `blindRating: RatingSummary | null` (null when there are no ratings yet).

## Timing document
Add `"language": "en" | "es"` (default `"en"`).
