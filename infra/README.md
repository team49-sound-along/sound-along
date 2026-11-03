# Sound Along infrastructure (AWS CDK v2, TypeScript)

One stack, `SoundAlongStack`, in us-west-2. Contract: `docs/AWS.md`.
Pinned: `aws-cdk-lib@2.273.0`, `constructs@10.5.0`, CDK CLI `aws-cdk@2.1147.0`.

## Layout
- `bin/app.ts` entry; optional context `alertEmail` creates the cost budget (skip it if the sandbox blocks AWS Budgets).
- `lib/sound-along-stack.ts` bucket, table, state machine, web deployment, outputs.
- `lib/cdn.ts` CloudFront distribution and behaviors. `lib/functions.ts` both Lambdas. `lib/budget.ts` AWS Budgets.
- `test/stack.test.ts` assertions (node:test via tsx). Fixtures under `test/fixtures` stand in for services/* and web/dist.

## Commands
```bash
cd infra && npm install
npm test                                   # unit tests, no AWS needed
npx cdk synth -c alertEmail=you@example.com
```

## Deploy (needs AWS credentials; nothing here has been deployed)
```bash
cd web && npm run build && cd ..           # web/dist is published to app/ (skipped with a warning if missing)
cd infra
npx cdk bootstrap aws://<ACCOUNT_ID>/us-west-2
npx cdk deploy -c alertEmail=you@example.com
```
Docker must be running for `cdk deploy` (builds the generator image, arm64). The API Lambda is bundled with local esbuild, no Docker.
After deploy: confirm the AWS Budgets subscription email, then seed:
`BUCKET=<BucketName> TABLE_NAME=<TableName> node services/api/scripts/seed.js`.
Tear down: `npx cdk destroy -c alertEmail=you@example.com` (bucket and table are DESTROY, sandbox only).

## Web client requirement: `x-amz-content-sha256` on /api writes
`/api/*` reaches the Lambda Function URL (AuthType `AWS_IAM`) through CloudFront Origin Access Control, which signs
requests with SigV4. For requests with a body (POST, PATCH, PUT) the signature covers the payload hash, and CloudFront
does not compute it for Lambda URL origins: Lambda rejects the request (403 "signature does not match") unless the
viewer supplies the header.

Decision: this cannot be fixed in infra. A CloudFront Function cannot read the request body, and Lambda@Edge would add
cost and complexity. The web client must send, on every POST/PATCH/PUT to `/api/*`:

```js
async function sha256Hex(body) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
const body = JSON.stringify(payload);
await fetch('/api/generate', {
  method: 'POST',
  headers: { 'content-type': 'application/json', 'x-amz-content-sha256': await sha256Hex(body) },
  body,
});
```
Rules: hash the exact string sent, lowercase hex, secure context only (https or localhost). Do not set an
`Authorization` header. GET and DELETE without a body need nothing. The distribution forwards the header via
`AllViewerExceptHostHeader`. Local dev (Express directly) ignores the header, so sending it always is safe.

## Notes
- `/data/*` uses a custom cache policy with an empty cache key: CloudFront handles `Range` natively, so MP3 seeking works.
- IAM is least privilege: object-level S3 actions on `raw/*` / `data/*` only, explicit DynamoDB actions, no `*` actions.
- Not covered by cdk-nag: no WAF, no access logs, no point-in-time recovery on the table (sandbox cost choices).
