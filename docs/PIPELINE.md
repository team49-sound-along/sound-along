# CI/CD pipeline (CodePipeline + CodeBuild)

The build and deploy run on AWS CodeBuild, not your laptop. The expensive part, building and pushing the 4.6 GB arm64
generator image, happens on managed ARM compute. A push to GitHub `main` triggers the whole thing.

This is defined in CDK as a second stack, `SoundAlongPipeline`, in the same `infra/` app. It is independent of
`SoundAlongStack`: deploying the pipeline once sets up the automation; the pipeline then deploys `SoundAlongStack` on
every push.

## What the pipeline does

```
GitHub (rohanreigns007/sound-along, main)
   |  push  -> CodeStar Connections (GitHub v2)
   v
CodePipeline
   +- Source          pull the repo
   +- BuildAndDeploy  one CodeBuild project (ARM, privileged = Docker), runs the same steps as infra/_deploy.ps1:
                        web:    npm ci && npm run build
                        api:    npm ci && python bundle_api.py
                        deploy: npx aws-cdk@2 deploy   (builds + pushes the generator image, then deploys the stack)
```

The CodeBuild environment is `aws/codebuild/amazonlinux2-aarch64-standard:3.0` (ARM), `BUILD_GENERAL1_LARGE`, privileged
mode on so CDK can run `docker build`. Native ARM means no slow QEMU emulation for the `linux/arm64` image.

## Deploy the pipeline (one time)

The pipeline is just another stack. Deploy it the same way you deploy `SoundAlongStack`, but name the pipeline stack and
pass the context you want the pipeline to use on every run:

```powershell
# from infra/, with sandbox credentials loaded (see _creds.ps1)
$env:JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION = "1"
$env:npm_config_registry = "https://registry.npmjs.org/"
$py = "c:\awshack\sound-along\infra\.venv\Scripts\python.exe"
npx --yes aws-cdk@2 deploy SoundAlongPipeline `
  -c ttsEngine=polly `
  -c alertEmail=team49_budgets@yopmail.com `
  --require-approval never `
  --app "$py app.py"
```

The `-c` flags are baked into the pipeline's buildspec, so they become the arguments the pipeline passes to `cdk deploy`
on every run. Defaults when omitted: `ttsEngine=kokoro`, `cmsHost=ec2`, no cost budget. Override the source with
`-c githubOwner=...`, `-c githubRepo=...`, `-c githubBranch=...` (defaults: `rohanreigns007` / `sound-along` / `main`).

## Authorize the GitHub connection (one time, manual, required)

CDK creates the GitHub connection in `PENDING` state. AWS requires a human to complete the OAuth handshake once; it cannot
be scripted. Until you do this, the pipeline's Source stage fails.

1. Open the AWS console in `us-west-2`: **Developer Tools > Settings > Connections** (or CodePipeline > Settings >
   Connections). The connection is named `sound-along-github`.
2. Select it, click **Update pending connection**.
3. Install/authorize the AWS Connector for GitHub app on the `rohanreigns007` account and grant it the `sound-along`
   repository.
4. The connection status flips to **Available**.

After it is `Available`, start the first run: push a commit to `main`, or in the console open the `sound-along-pipeline`
pipeline and click **Release change**.

## Watch a run

- CodePipeline console > `sound-along-pipeline` shows the two stages.
- Click the `BuildAndDeploy` action > **Details** to tail the CodeBuild log (the web build, the bundle, the Docker image
  push, and the CDK deploy output all stream here).
- On success, the stack outputs (`SiteUrl`, `BucketName`, etc.) are printed near the end of the CodeBuild log and captured
  as the build artifact `infra/_outputs.json`.

Seeding demo content (`services/api/scripts/seed.js`) and verification (`scripts/verify_deployment.py`) are **not** part of
the pipeline; run those as before once the stack is deployed (see `docs/DEPLOY.md`).

## IAM

The CodeBuild role is granted `sts:AssumeRole` on the CDK bootstrap roles (`cdk-hnb659fds-*`) so `cdk deploy` works without
giving CodeBuild broad admin. The account must already be CDK-bootstrapped (it is, from the local deploys). The pipeline
and its artifact bucket use `RemovalPolicy.DESTROY` with `autoDeleteObjects`, so `cdk destroy SoundAlongPipeline` leaves
nothing behind in the sandbox.

## Tear down

```powershell
npx --yes aws-cdk@2 destroy SoundAlongPipeline --app "$py app.py"
```

This removes the pipeline, the CodeBuild project, the artifact bucket, and the GitHub connection. It does **not** touch
`SoundAlongStack` (destroy that separately, see `docs/DEPLOY.md`).

## Notes and gotchas

- **Local toolchain for deploying the pipeline:** the jsii kernel does not start cleanly on Node 24 with this repo's
  Python 3.14 venv, and the CDK CLI rejects Node 20 as end-of-life. Use **Node 22** locally (`nvm use 22`) to run
  `cdk deploy`/`synth`. This only affects your machine; CodeBuild pins Node 18 in the buildspec.
- **Private npm registry:** the default npm registry here is an internal proxy that does not resolve off-network. Set
  `npm_config_registry=https://registry.npmjs.org/` before any `npx aws-cdk` call (mirrors `_deploy.ps1`).
- **First run is slow** (same 4.6 GB image push as a cold local deploy). Later runs reuse ECR layers, so only real changes
  to the generator rebuild.
- The `cmsHost=ec2` default deploys the VM option. Add `-c cmsHost=lambda` when deploying the pipeline for the cheaper
  idle Lambda CMS.
