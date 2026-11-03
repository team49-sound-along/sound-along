# Sound Along on AWS: shared contract (v1)

Region `us-west-2`. Everything is serverless and idle-cost-free. No VPC, no NAT Gateway, no always-on compute.

```
Browser -> CloudFront (OAC) --+-- default behavior  -> S3  (originPath /app)      static Vue build
                              +-- /data/*           -> S3  (no originPath)        audio + timing
                              +-- /api/*            -> Lambda Function URL (AWS_IAM, OAC)  = API Lambda (Express 4, Node 22)
API Lambda --StartExecution--> Step Functions (Standard) --> Generator Lambda (container image, arm64, Python 3.12, Kokoro baked in)
Generator Lambda --> S3 (data/*), DynamoDB (job progress + passage summary)
API Lambda --> DynamoDB (assignments, events, jobs, passages)
AWS Budgets (email alerts) + reserved concurrency on both Lambdas
```

## S3 bucket (private, block public access, OAC only)
| Key | Content |
|---|---|
| `app/**` | built web app (`web/dist`), deployed by CDK `BucketDeployment` |
| `data/{passageId}.mp3` | 64 kbps CBR mono MP3 (`Content-Type: audio/mpeg`) |
| `data/{passageId}.timing.json` | timing document, see docs/API.md (`Content-Type: application/json`) |
| `raw/{passageId}.json` | generator input `{ uuid, title, content (HTML), source: "generated" }` |

`passageId` is a UUID (`[0-9a-f-]{36}`).

## DynamoDB single table (`TABLE_NAME`), on-demand, partition key `pk` (S), sort key `sk` (S)
| Item | pk | sk | Attributes |
|---|---|---|---|
| Passage summary | `PASSAGE` | `{passageId}` | all `Passage` fields from docs/API.md (id, title, words, durationMs, engine, voice, createdAt, source, vocabCount, pairId) + `metrics` (the metrics object from the timing document) |
| Assignment | `ASSIGNMENT` | `{assignmentId}` | all `Assignment` fields from docs/API.md |
| Quality report | `QUALITY` | `REPORT` | `report`: the object from `data/quality-report.json` (written by `scripts/build_samples.py`, loaded by `services/api/scripts/seed.js`) |
| Event totals | `EVENTS` | `TOTALS` | numeric `plays`, `wordTaps`, `completions`; increment with `ADD` |
| Job | `JOB` | `{jobId}` | all `Job` fields from docs/API.md, plus `ttl` (epoch seconds, 7 days) |

Classes are synthetic constants in code (the `CLASSES` list in `services/api/src/stores/fileStore.js`); not stored.

## Step Functions
Standard state machine `GenerateStateMachine`: one Task state invoking the Generator Lambda with the execution input, retry once on Lambda service errors, no other states. Input:
`{ "jobId": "uuid", "passageId": "uuid", "title": "string", "rawKey": "raw/{passageId}.json" }`

## Generator Lambda (`services/generator`)
Container image (arm64). Handler `handler.handler`. For each event: mark the job `running`/`parse`, read `rawKey` from S3, run the pipeline from `services/synth` (`pipeline.generate`, `engine.KokoroEngine`, `run_local._encode_mp3`/metrics helpers may be refactored into importable functions), updating the job item `step` to `parse`, `synthesize`, `align`, `publish` as stages run, upload `data/{passageId}.mp3` and `data/{passageId}.timing.json`, write the PASSAGE summary item, then mark the job `done` with `metrics` and `finishedAt`. On any exception: log it, mark the job `failed` with the friendly error string used by `services/api/src/jobs/localRunner.js`, and return normally (do not raise). Model weights and the spaCy model are baked into the image; the function must work with no outbound internet. Memory 4096 MB, timeout 600 s, reserved concurrency 2. Lazy-load the model inside the handler on first use (Lambda init limit is 10 s).

Environment: `BUCKET`, `TABLE_NAME`.

## API Lambda (`services/api`)
Entry `src/aws/lambda.js`, export `handler`. Node 22, arm64, 512 MB, 30 s, reserved concurrency 5. Express app from `createApp` wired with AWS adapters (DynamoDB store, DynamoDB-backed catalog and job store, Step Functions runner). Function URL auth type `AWS_IAM`, invoked only by CloudFront (OAC). Environment: `BUCKET`, `TABLE_NAME`, `STATE_MACHINE_ARN`, `GENERATION_ENABLED` ("true"/"false"), `GENERATE_PER_MINUTE`, `MAX_CONCURRENT_JOBS`. `/data/*` and the web app are served by CloudFront from S3, so on Lambda `createApp` is created with no `webDist` and no `/data` route needed (the route can remain but must not read local disk when `config.dataDir` is unset).

## IAM (least privilege)
API Lambda: DynamoDB read/write on the table, `states:StartExecution` on the state machine, `s3:PutObject` on `raw/*`. Generator Lambda: `s3:GetObject` on `raw/*`, `s3:PutObject` on `data/*`, DynamoDB read/write on the table. CloudFront: read the bucket via OAC and invoke the API Function URL via OAC.

## Seeding
`services/api/scripts/seed.js` uploads every `data/{uuid}.mp3` and `data/{uuid}.timing.json` from the local `data/` folder to the bucket and writes the PASSAGE summary items, so the deployed site shows the three sample passages without running the generator. Usage: `BUCKET=... TABLE_NAME=... node scripts/seed.js`.
