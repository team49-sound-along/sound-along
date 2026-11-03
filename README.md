# Sound Along

Read-along narration for K-12 passages, built for the [ReadWorks](https://www.readworks.org) challenge at AWS Breaking Barriers 2026 (NYC, Team 49).

A student presses play and every word is highlighted as it is spoken. Tapping any word replays from that word. Passage text becomes narration and word-level timing automatically, with no manual editing. Where ReadWorks already has a human recording, the same highlighting is added to it, and the reader can switch between the human narrator and the AI voice.

## What it does
- **Text to narration, automatically.** Open-source voice (Kokoro-82M, Apache-2.0) with an editable pronunciation overrides file and loudness matching.
- **Word-level timing and live highlighting.** Tap a word to play from it. Arrow keys move between words (one tab stop), Enter or Space plays.
- **Existing human recordings get highlighting** with no regeneration (Whisper alignment), plus a Human / AI voice toggle that keeps the reader's place.
- **Word help** while reading: definition, part of speech, examples and Spanish translations, taken from the passage's own vocabulary data.
- **Teacher view:** assign a passage to a class and switch Sound Along on or off. Students whose teacher turned it off see the text without audio.
- **Generate:** paste text, watch the four pipeline steps run, open the result in the reader.
- **Insights:** measured quality, cost comparison and classroom adoption, with each number labelled by how it was measured.

## Architecture
```
Browser (Vue 3) -> CloudFront (OAC) -+- /app/*  -> S3 (static web app)
                                     +- /data/* -> S3 (MP3 + timing JSON)
                                     +- /api/*  -> API Lambda (Express 4, Node 22) -> DynamoDB
API Lambda -> Step Functions -> Generator Lambda (container, arm64, Kokoro baked in, no internet needed)
                                  parse -> synthesize per sentence -> align words -> master audio -> publish to S3
```
Details: `docs/AWS.md` (AWS contract), `docs/API.md` (HTTP contract), `docs/COST.md` (long-run cost), `infra/README.md` (deploy).

## Run it locally (no AWS needed)
Prerequisites: Python 3.12, Node 18 or newer (the customer requires 18.x; see `.nvmrc`), and `uv`. No ffmpeg is needed.
```bash
scripts/dev.sh          # installs, builds the samples, serves http://127.0.0.1:3101
```
Rebuild every sample and every measured number from scratch (about 3 minutes): `.venv/bin/python scripts/build_samples.py`

Tests: `cd services/parse && ../../.venv/bin/python -m pytest` (same for `synth`, `eval`, `align`, `generator`), `cd services/api && npm test`, `cd web && npm test`, `cd infra && npm test`.

## Deploy to AWS
Region `us-west-2`. Docker must be running (the generator is a container image).
```bash
cd web && npm run build && cd ../infra && npm install
npx cdk bootstrap aws://<ACCOUNT_ID>/us-west-2
npx cdk deploy                      # add -c alertEmail=you@example.com to also create a monthly cost budget
BUCKET=<BucketName output> TABLE_NAME=<TableName output> node ../services/api/scripts/seed.js
```
The cost budget is optional because some sandbox accounts block the Budgets API.

## Measured results
All from `data/quality-report.json`, written by `scripts/build_samples.py` for the three bundled passages (2,319 words checked). The ASR check compares our timing and text with an independent Whisper transcript. It is agreement between two systems, not ground truth.

| Measure | Result |
|---|---|
| Word error vs an independent transcript | 1.6% (most differences are British vs American spelling in the Austen text) |
| Word timing difference, median | 60 ms |
| Word timing difference, 95th percentile | 185 ms |
| Words within 100 ms / 250 ms | 82% / 97% |
| Existing human recordings aligned automatically | Park Caretaker 356 of 360 words exact; Tea Party 821 of 830 (the Tea Party audio carries ReadWorks' human-audio flag; I have not listened to confirm) |
| Predicted naturalness (UTMOS, 1 to 5): our voice | 4.50 (Park Caretaker), 4.51 (Pride and Prejudice) |
| Same predictor on ReadWorks' current Polly audio | 4.05 (Pride and Prejudice) |
| Same predictor on the ReadWorks human recording | 3.19 (Park Caretaker; recording noise lowers this score) |

Honest limits:
- Naturalness is a **predictor**, not a listening test, and it rewards clean audio. It does not show that the voice feels human to a child. Run a blind listening test with ReadWorks staff before making that claim.
- Generation speed (about 0.06 seconds of compute per second of audio) was measured on a laptop, not on Lambda. The Lambda cost shown in the app is an estimate with its assumption stated.
- Phone-width layout and a deployed run through CloudFront have not been verified yet.

## Cost
Reading is served from static files, so the cost that grows with usage is audio delivery. See `docs/COST.md`. The MP3 bitrate is a setting (`SOUND_ALONG_MP3_KBPS`, default 48).

## Following the ReadWorks technical guide
| Guide says | What we do |
|---|---|
| Python 3.14 for audio generation and product JSON | The generator image runs Python 3.14.10 (the `python3.14` Lambda base image). Kokoro declares support for 3.10 to 3.12 only, so it is installed with `--ignore-requires-python`; `scripts/smoke_generator_image.sh` proves the image works with no network (handler, synthesis, extra voices, recognition). Local development uses 3.12, where Kokoro is officially supported. |
| Node 18.x, Express 4.x, Vue 3.x | All three. API and web tests pass on Node 18.20.8 (`.nvmrc`). Note that AWS deprecated `nodejs18.x` on Sep 1, 2025 (no security patches); creating Lambda functions with it through CDK stays allowed until Jul 29, 2027. |
| AWS CDK 2.x, us-west-2, single account | Yes. |
| Serverless for TTS, VM for content management, browser client | TTS is a Lambda container behind Step Functions. The content-management API runs on an EC2 VM by default; a Lambda option exists for lower idle cost (see `infra/README.md`). |
| Timing in S3 "in zipped form" | Timing JSON is stored gzipped with `Content-Encoding`, so browsers decompress it transparently. |
| Frontend reads JSON documents and only presents | The reader reads the S3 documents (`docs/FORMAT.md`). The library list and the teacher screens use the API. |
| Minimal libraries, JS-native preferred | The web app has one runtime dependency (Vue). |

## Pronunciation fixes
Edit `services/synth/pronunciations.json`: a word and a plain-English respelling (or `/phonemes/`). The passage still shows and highlights the original spelling. `scripts/build_samples.py` lists words the independent transcript heard differently, as candidates.

## Switching the voice engine
`TTS_ENGINE=kokoro` (default) or `TTS_ENGINE=polly` (Amazon Polly Neural; needs AWS credentials and bills the text twice, once for audio and once for word marks). The Polly engine is covered by unit tests with a fake client; it has not been run against the real service.

## License
MIT for this project's code (`LICENSE`). Third-party components and content are listed in `NOTICE.md`. ReadWorks passage text belongs to ReadWorks.
