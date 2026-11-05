# Sound Along

Read-along narration for K-12 passages, built for the [ReadWorks](https://www.readworks.org) challenge at AWS Breaking Barriers 2026 (NYC, Team 49).

A student presses play and every word is highlighted as it is spoken. Tapping any word replays from that word. Passage text becomes narration and word-level timing automatically, with no manual editing. Where ReadWorks already has a human recording, the same highlighting is added to it, and the reader can switch between the human narrator and the computer-generated read-aloud voice.

## What it does
- **Any teacher content, on demand.** Paste a passage or upload a `.txt`/`.md` file, optionally with your own recording. Parsing, narration, word timing and publishing run automatically. A recording is aligned into a linked human-narrated variant.
- **English and Spanish.** Kokoro speaks both, and two Phonon voices (Hadley, Everly) are offered in English. It gives word timing for English only, so Spanish word times come from a multilingual Whisper pass.
- **Nothing hardcoded for voice and pronunciation.** Voice, speed and MP3 quality are stored Settings. Pronunciation fixes are stored data a teacher edits. An automatic check lists candidate mispronounced words for review (candidates, not confirmed mistakes), and a fix plus "regenerate" closes the loop.
- **Word-level timing and live highlighting.** Tap a word to play from it. "Hear this word" plays just that word. Arrow keys move between words (one tab stop), Enter or Space plays.
- **Existing human recordings get highlighting** with no regeneration (Whisper alignment), plus a Recorded narrator / read-aloud voice toggle that keeps the reader's place.
- **Word help** while reading: definition, part of speech, examples and Spanish translations, taken from the passage's own vocabulary data.
- **Teacher view:** assign a passage to a class and switch Sound Along on or off. Students whose teacher turned it off see the text without audio.
- **Blind listening test.** Anonymous clips of the same text, loudness-matched and identically encoded; ratings feed Insights, which is the vision document's narration-quality metric.
- **Insights:** measured quality, cost comparison and classroom adoption, with each number labelled by how it was measured.

## Architecture
```
Browser (Vue 3) -> CloudFront (OAC) -+- /app/*  -> S3 (static web app)
                                     +- /data/* -> S3 (MP3 + timing JSON)
                                     +- /api/*  -> API Lambda (Express 4, Node 18.x) -> DynamoDB
API Lambda -> Step Functions -> Generator Lambda (container, arm64, Kokoro and Phonon baked in, no internet needed)
                                  parse -> synthesize per sentence -> align words -> master audio -> publish to S3
```
Details: `infra/README.md` (infrastructure).

## Run it locally (no AWS needed)
Prerequisites: Python 3.12 for local development only (Kokoro supports Python 3.10 to 3.12; the deployed generator image runs the required Python 3.14), Node 18 or newer (the customer requires 18.x; see `.nvmrc`), and `uv`. No ffmpeg is needed.
```bash
scripts/dev.sh          # installs, builds the samples, serves http://127.0.0.1:3101
```
Rebuild every sample and every measured number from scratch (about 3 minutes, plus the Spanish/English translations it makes at the end): `.venv/bin/python scripts/build_samples.py`. Order matters: the translations, cards and pictures are build output, so build before seeding or demoing.

Tests: `cd services/parse && ../../.venv/bin/python -m pytest` (same for `synth`, `eval`, `generator`, `scripts`), `cd services/api && npm test`, `cd web && npm test`, and for the infrastructure (Python) `cd infra && python -m pytest`.

## AWS services used
Everything is defined in `infra/` (AWS CDK 2, Python, region us-west-2). The stack synthesizes and passes its infrastructure tests; deploy steps are below.

| Service | What it does here | Default? |
|---|---|---|
| Amazon S3 | Private bucket for the web app and every generated file (audio, word timing, cards) | on |
| Amazon CloudFront | One address for the web app, `/data/*` (audio and timing, byte-range playback) and `/api/*` | on |
| AWS Lambda | The API, the generator (a container image: narration, word timing, translation) and the question-drafting function | on |
| AWS Step Functions | One run per passage: generate the audio, then make the other-language version. A long text is narrated in internal chunks and joined into one passage | on |
| Amazon DynamoDB | Jobs, passage summaries, settings, pronunciations, assignments, activity and listening ratings | on |
| Amazon EC2 | The content-management API on a small VM (`-c cmsHost=lambda` runs it on Lambda instead) | on |
| Amazon ECR, IAM, CloudWatch Logs | The generator image, least-privilege roles, logs | on |
| Amazon Polly | Narration in place of the built-in voices (`-c ttsEngine=polly`, `pollyVoice`, `pollyVoiceEs`, `pollyEngine`) | off |
| Amazon Translate | Sentence translation in front of the built-in translator (`-c translateModel=amazon`) | off |
| Amazon Bedrock | Practice-question drafting (`-c questionsModel=bedrock:<modelId>`) and an optional context-aware translator (`-c translateModel=bedrock:<modelId>`) | off |
| AWS Budgets | A cost alert (`-c alertEmail=you@example.com`) | off |
| AWS CodePipeline and CodeBuild | Optional CI/CD stack that deploys on every push to `main` (`infra/sound_along/pipeline_stack.py`, `docs/PIPELINE.md`) | separate stack |

The optional services are off unless you switch them on, and each adds only the one permission it needs (for example `polly:SynthesizeSpeech`).

## Deploy to AWS
Region `us-west-2`. Docker must be running (the generator is a container image). The infrastructure is AWS CDK 2.x in Python. In short:
```bash
cd web && npm run build && cd ../infra
uv venv --python 3.14 && source .venv/bin/activate && pip install -r requirements-dev.txt
python bundle_api.py
npx aws-cdk@2 bootstrap aws://<ACCOUNT_ID>/us-west-2
npx aws-cdk@2 deploy                 # content-management API on a VM (the guide's default); add -c cmsHost=lambda for the cheaper idle option
BUCKET=<BucketName output> TABLE_NAME=<TableName output> node ../services/api/scripts/seed.js
python ../scripts/verify_deployment.py --site <SiteUrl output> --generate
```
The cost budget is optional (`-c alertEmail=you@example.com`) because some sandbox accounts block the Budgets API.

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
Reading is served from static files, so the cost that grows with usage is audio delivery. The MP3 bitrate is a setting (`SOUND_ALONG_MP3_KBPS`, default 48).

## Following the ReadWorks technical guide
| Guide says | What we do |
|---|---|
| Python 3.14 for audio generation and product JSON | The generator image runs Python 3.14.10 (the `python3.14` Lambda base image). Kokoro declares support for 3.10 to 3.12 only, so it is installed with `--ignore-requires-python`; `scripts/smoke_generator_image.sh` proves the image works with no network (handler, synthesis, extra voices, recognition). Local development uses 3.12, where Kokoro is officially supported. |
| Node 18.x, Express 4.x, Vue 3.x | All three. API and web tests pass on Node 18.20.8 (`.nvmrc`). Note that AWS deprecated `nodejs18.x` on Sep 1, 2025 (no security patches); creating Lambda functions with it through CDK stays allowed until Jul 29, 2027. |
| AWS CDK 2.x, us-west-2, single account | Yes. |
| Serverless for TTS, VM for content management, browser client | TTS is a Lambda container behind Step Functions. The content-management API runs on an EC2 VM by default; a Lambda option exists for lower idle cost (see `infra/README.md`). |
| Timing in S3 "in zipped form" | Timing JSON is stored gzipped with `Content-Encoding`, so browsers decompress it transparently. |
| Frontend reads JSON documents and only presents | The reader reads the S3 documents. The library list and the teacher screens use the API. |
| Minimal libraries, JS-native preferred | The web app has one runtime dependency (Vue). |

## Pronunciation fixes
Edit `services/synth/pronunciations.json`: a word and a plain-English respelling (or `/phonemes/`). The passage still shows and highlights the original spelling. `scripts/build_samples.py` lists words the independent transcript heard differently, as candidates.

## Switching the voice engine
On AWS the default narration engine is **Amazon Polly** (`-c ttsEngine=polly`, voices Joanna and Lupe, neural), and teachers can choose another Polly voice or the built-in voices (Kokoro and Phonon) per deployment in Settings. Polly bills the text twice (once for audio and once for word marks); requests are paced and retried when the account's rate limit (8 a second) is reached. `TTS_ENGINE=kokoro` runs the open-source voices instead: they work on a laptop and are what the committed sample passages were narrated with, but they do not run reliably inside Lambda (PyTorch cannot read the CPU list there), so the live site uses Polly. A word's teacher pronunciation (a plain respelling or `/IPA/`) works with both engines. Foreign names and words inside a passage are read by the other language's voice (Lupe for a Spanish name in English text).

Everything measured in the quality table above was measured with Kokoro. The same measurements for Polly have not been run yet.

## License
MIT for this project's code (`LICENSE`). Third-party components and content are listed in `NOTICE.md`. ReadWorks passage text belongs to ReadWorks.
