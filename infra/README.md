# Sound Along infrastructure (AWS CDK v2, Python)

One stack, `SoundAlongStack`, in us-west-2, single account.
Pinned: `aws-cdk-lib==2.273.0`, `constructs==10.5.0`, CDK CLI `aws-cdk@2` (tested with 2.1147.0), esbuild 0.25.10.

**Python 3.14** (the customer's requirement) works: `uv venv --python 3.14`, then `pip install -r requirements-dev.txt`
installs aws-cdk-lib 2.273.0 with jsii 1.142.0 on CPython 3.14.7 with no errors, and the full test suite passes there.
jsii also needs Node (22 or 24 are its supported versions; newer Node prints an "untested" warning, silence it with
`JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1`).

## Two ways to host the CMS API (context `cmsHost`)
| | `ec2` (default) | `lambda` |
|---|---|---|
| CMS runs on | one t4g.small VM (Express on Node 18.20.8, systemd) | Lambda, Node 18.x, behind a Function URL |
| `/api/*` origin | CloudFront -> HTTP :8080 to the instance's public DNS | CloudFront -> Function URL via OAC (SigV4) |
| Idle cost | about $16 / month | about $0 |

Why the VM is the default: the customer's technical document says "Serverless for TTS, VM for content management, Browser
client for audio playback + highlighting". TTS generation stays serverless (Step Functions + container Lambda) in both modes.
Lambda stays available as an alternative.

Honest cost note (us-west-2, rough): VM idle is about $16/month = t4g.small about $12 + public IPv4 about $3.6 + 8 GB gp3
about $0.6. Lambda idle is about $0 (pay per request). Both add the same CloudFront, S3, DynamoDB and Step Functions usage.

### What `ec2` mode creates
- VPC with 1 AZ, ONE public subnet, NO NAT gateway, no private subnets.
- Security group: no SSH (22). Ingress TCP 8080 only from the CloudFront origin-facing managed prefix list
  (`com.amazonaws.global.cloudfront.origin-facing`); its id is resolved at deploy time by an AwsCustomResource calling
  `ec2:DescribeManagedPrefixLists` (policy limited to that single action).
- Instance: t4g.small, Amazon Linux 2023 arm64 (latest AMI from the public SSM parameter), IMDSv2 required, 8 GB gp3
  encrypted root volume, public IPv4. Access is by SSM Session Manager only.
- Instance role = the API Lambda's grants and nothing wider: DynamoDB read/write on the table, `states:StartExecution`,
  `s3:PutObject` and `s3:GetObject` on `raw/*` (presigned recording uploads, regenerate), read of its own app asset, plus
  the AmazonSSMManagedInstanceCore managed policy. No `*` actions.
- First boot (user data): download Node.js v18.20.8 linux-arm64 and verify its sha256 before extracting, fetch the app
  bundle with the AWS CLI, run `node serverVm.js` as the non-root `soundalong` user under systemd (`Restart=always`).
  Changing the app bundle changes the user data, which replaces the instance.
- Outputs: `CmsInstanceId` and `CmsSessionCommand` (`aws ssm start-session --target <id> --region us-west-2`).

The VM origin needs no `x-amz-content-sha256` header (that is only for the Lambda URL with OAC). The web client sends it
anyway; Express ignores it, so it is harmless.

Caveat: the origin is the instance's public DNS name, which changes if the instance is stopped and started (a reboot keeps
it). Run `cdk deploy` again after a stop/start, or add an Elastic IP if the VM must be stoppable.

### `lambda` mode
Unchanged architecture: Function URL (AuthType `AWS_IAM`) + OAC, reserved concurrency 5, 512 MB, 30 s. Runtime is
**nodejs18.x** (the customer's required Node 18.x). AWS deprecated nodejs18.x on Sep 1 2025, but creating functions through
CloudFormation/CDK stays allowed until Jul 29 2027, so it is acceptable for this event and must be revisited afterwards.

## Layout
- `app.py` entry. Context: `cmsHost` (`ec2` | `lambda`, validated), `alertEmail` (optional cost budget).
- `sound_along/stack.py` bucket, table, wiring. `cms_vm.py` VPC, SG, role, instance, user data. `cdn.py` CloudFront.
  `functions.py` Lambdas. `pipeline.py` state machine. `budget.py`, `config.py`, `iam_util.py`.
- `bundle_api.py` bundles `services/api` with esbuild into `build/api-lambda` and `build/api-vm` (both include
  `config/voices.json`). The stack raises a clear error if the folder it needs is missing.
- `tests/` pytest with `aws_cdk.assertions`; fixtures under `tests/fixtures` stand in for the bundles, generator and `web/dist`.

## Commands
```bash
cd infra
uv venv --python 3.14 && source .venv/bin/activate    # or: python3.14 -m venv .venv
pip install -r requirements-dev.txt
(cd ../services/api && npm ci)                         # the bundle needs express and the AWS SDK
python bundle_api.py                                   # esbuild -> build/
python -m pytest                                       # unit tests, no AWS needed
npx aws-cdk@2 synth -c alertEmail=you@example.com                  # ec2 (default)
npx aws-cdk@2 synth -c alertEmail=you@example.com -c cmsHost=lambda
```

## Deploy (needs AWS credentials; nothing here has been deployed)
```bash
cd web && npm run build && cd ../infra     # web/dist is published to app/ (skipped with a warning if missing)
source .venv/bin/activate && python bundle_api.py
npx aws-cdk@2 bootstrap aws://<ACCOUNT_ID>/us-west-2

# VM (default)
npx aws-cdk@2 deploy -c alertEmail=you@example.com
# Lambda alternative
npx aws-cdk@2 deploy -c alertEmail=you@example.com -c cmsHost=lambda
```
Docker must be running for deploy (builds the generator image, arm64). After deploy: confirm the AWS Budgets email, then seed:
`BUCKET=<BucketName> TABLE_NAME=<TableName> node services/api/scripts/seed.js`.
Open a shell on the VM: run the `CmsSessionCommand` output. Logs: `journalctl -u sound-along`.
Tear down: `npx aws-cdk@2 destroy -c alertEmail=you@example.com` (bucket and table are DESTROY, sandbox only).
Switching `cmsHost` on an existing stack replaces the API origin; expect a CloudFront update of a few minutes.

## Web client requirement (lambda mode only): `x-amz-content-sha256` on /api writes
With the Function URL (AuthType `AWS_IAM`) behind OAC, CloudFront signs requests with SigV4. For requests with a body
(POST, PATCH, PUT) the signature covers the payload hash, which CloudFront does not compute for Lambda URL origins, so the
viewer must send `x-amz-content-sha256` (lowercase hex SHA-256 of the exact body string; secure context only; do not set
`Authorization`). A CloudFront Function cannot read the body and Lambda@Edge adds cost, so this cannot be fixed in infra.

```js
async function sha256Hex(body) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
```
The distribution forwards the header via `AllViewerExceptHostHeader`. Local dev and the VM ignore it.

## Notes
- `/data/*` uses a custom cache policy with an empty cache key: CloudFront handles `Range` natively, so MP3 seeking works.
- IAM is least privilege: object-level S3 actions on `raw/*` / `data/*` only, explicit DynamoDB actions, no `*` actions.
- Not covered by cdk-nag: no WAF, no access logs, no point-in-time recovery on the table (sandbox cost choices).
