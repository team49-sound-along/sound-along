# Deploy day runbook (AWS sandbox, us-west-2)

Nothing in this repository has run on AWS yet. This runbook is written so the first deploy takes minutes and every piece is
checked afterwards. Allow 30 to 45 minutes for the first run; the slow part is pushing the 4.6 GB generator image.

## Before you start (5 minutes)
- [ ] Sandbox access from the AWS team lead (Workshop Studio, $500 cap, us-west-2 or us-east-1 only).
- [ ] `aws sts get-caller-identity` shows the sandbox account (use the credentials from the Workshop Studio page).
- [ ] Docker Desktop running; `docker info` works. The venue Wi-Fi decides how long the image push takes.
- [ ] Python 3.14 (`uv venv --python 3.14`), Node 18 or newer, `npx` available.
- [ ] `data/` is built: `.venv/bin/python scripts/build_samples.py` (about 6 minutes) so there is something to seed.
- [ ] Bedrock is not used, so no model access is needed. Polly is optional (`TTS_ENGINE=polly`).

## 1. Deploy
```bash
cd web && npm install && npm run build && cd ..
cd infra
uv venv --python 3.14 && source .venv/bin/activate
pip install -r requirements-dev.txt
(cd ../services/api && npm ci)
python bundle_api.py                                      # esbuild bundles for the Lambda and VM options
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1
npx aws-cdk@2 bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-west-2
npx aws-cdk@2 deploy -c alertEmail=<an address you read>    # VM default (the customer's "VM for content management")
```
- If the sandbox blocks the Budgets API the deploy fails: deploy again WITHOUT `-c alertEmail=...` (the budget is optional).
- Cheaper idle option: add `-c cmsHost=lambda` (Lambda instead of the VM; about $0 idle instead of about $16 a month).
- Note the outputs: `SiteUrl`, `BucketName`, `TableName`, `StateMachineArn`, and (VM) `CmsInstanceId`.

## 2. Seed the demo content
```bash
cd ../services/api && npm ci
BUCKET=<BucketName> TABLE_NAME=<TableName> node scripts/seed.js
```
This uploads the audio, gzipped timing, the listening-test clips under `data/ab/` and the quality report.

## 3. Verify everything (the script does the checking)
```bash
python scripts/verify_deployment.py --site <SiteUrl> --generate                 # English job end to end
python scripts/verify_deployment.py --site <SiteUrl> --generate --language es   # Spanish job end to end
```
It checks: the site loads; the API answers; passages are listed; timing is valid and monotonic (and reports gzip); an audio
Range request returns 206 (seeking works); a write succeeds through CloudFront with the `x-amz-content-sha256` header; security
headers; Insights; the listening clips; and a real generation job through Step Functions and the generator Lambda.

Expected, per mode:
- VM: the write works with and without the hash header.
- Lambda + OAC: the write works WITH the header and returns 403 without it. That is correct; the web client always sends it.

## 4. Replace estimates with measurements (the vision document asks for cost per passage)
After the `--generate` runs, read the generator's real numbers from CloudWatch:
```bash
aws logs tail /aws/lambda/<generator function name> --since 30m --filter-pattern REPORT --region us-west-2
```
Each `REPORT` line gives **Billed Duration** and **Max Memory Used**. Cost per passage = Billed Duration (s) x memory (GB) x
$0.0000166667 (x86; arm64 is about 20% less). Put the measured number in the demo; the app's "estimated Lambda" figure assumes
a 5x slowdown versus the dev laptop and is not a measurement.

## 5. Check the things only a person can check
- [ ] Open `SiteUrl`; read a passage; tap a word; switch Recorded narrator / read-aloud voice; open a Spanish passage.
- [ ] Listening test: rate a few clips (this builds the narration-quality metric).
- [ ] Phone: open `SiteUrl` on a real phone; play audio (iOS Safari autoplay rules).
- [ ] Reset test traffic before the demo: Insights adoption counts include your own clicks.

## If something fails
| Symptom | Likely cause | Fix |
|---|---|---|
| Deploy fails at the Budget | Billing API blocked in the sandbox | Redeploy without `-c alertEmail` |
| Image push is very slow | 4.6 GB over venue Wi-Fi | Start the deploy first thing; do other work meanwhile |
| `/api/*` returns 502/504 (VM) | Instance still booting, or user data failed | `aws ssm start-session --target <CmsInstanceId>`, then `sudo journalctl -u soundalong -n 80` and `sudo cloud-init status --long` |
| `/api/*` returns 403 (Lambda) | OAC permission on the Function URL | Confirm the CDK deploy completed; POSTs must send `x-amz-content-sha256` |
| Generate job stays `queued` | State machine could not start | Check `GENERATION_ENABLED`, the state machine execution history |
| Job `failed` with the friendly message | Generator error | `aws logs tail` on the generator function |
| Audio will not seek | CDN returned 200 not 206 | Serve MP3 from S3 via CloudFront, not from the API |
| After stopping and starting the VM, `/api` fails | The VM's public DNS changed | Deploy again (see `infra/README.md`) |

## Tear down
```bash
cd infra && source .venv/bin/activate && npx aws-cdk@2 destroy
```
The sandbox is wiped at the end of the event anyway. Export anything you want to keep (the repo has the code; audio rebuilds with
`scripts/build_samples.py`).

## Known unverified (be honest in the demo)
The user data on a real instance, the CloudFront prefix-list custom resource, the OAC-signed POST path, the cold start of the
generator container, and real Lambda cost per passage. This runbook exists to turn those into measured facts.
