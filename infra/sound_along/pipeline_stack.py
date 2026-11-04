"""CI/CD pipeline that builds and deploys SoundAlongStack on AWS, not the local laptop.

GitHub (via a CodeStar Connections v2 connection) -> CodePipeline -> a single CodeBuild
project that reproduces infra/_deploy.ps1:

    web:    npm ci && npm run build          (Vite build -> web/dist)
    api:    npm ci && python bundle_api.py    (esbuild -> infra/build/api-{lambda,vm})
    deploy: cdk deploy                        (CDK builds+pushes the 4.6 GB generator image)

The generator image is linux/arm64, so the build runs on an ARM CodeBuild image with
privileged mode enabled (CDK shells out to `docker build`). Native ARM avoids slow emulation.

One-time manual step: the GitHub connection is created PENDING. Authorize it once in the
console (CodePipeline > Settings > Connections > Update pending connection) before the first run.
"""
from __future__ import annotations

from dataclasses import dataclass

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as cpactions
from aws_cdk import aws_codestarconnections as codestar
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .config import PROJECT_TAG, REGION

# The generator Dockerfile pins Python 3.14; CodeBuild's ARM standard image ships a usable
# Python/Node, and we install the exact Node from .nvmrc and CDK deps in the buildspec.
_ARM_BUILD_IMAGE = codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0


@dataclass(frozen=True)
class PipelineStackProps:
    """Inputs for the CI/CD pipeline.

    github_owner/github_repo/github_branch: the source repo and branch to deploy.
    tts_engine: passed to `cdk deploy -c ttsEngine=...` (kokoro default, polly optional).
    cms_host: passed to `cdk deploy -c cmsHost=...` (ec2 default, lambda optional).
    alert_email: when set, passed to `cdk deploy -c alertEmail=...` (optional cost budget).
    """

    github_owner: str
    github_repo: str
    github_branch: str = "main"
    tts_engine: str | None = None
    cms_host: str | None = None
    alert_email: str | None = None


def _buildspec(props: PipelineStackProps) -> codebuild.BuildSpec:
    """Reproduce infra/_deploy.ps1 as a Linux buildspec."""
    context_flags = ["--require-approval never"]
    if props.tts_engine:
        context_flags.append(f"-c ttsEngine={props.tts_engine}")
    if props.cms_host:
        context_flags.append(f"-c cmsHost={props.cms_host}")
    if props.alert_email:
        context_flags.append(f"-c alertEmail={props.alert_email}")
    # Write the stack outputs so the declared artifact (infra/_outputs.json) exists; without --outputs-file the file
    # is never created and UPLOAD_ARTIFACTS fails with "no matching artifact paths found".
    context_flags.append("--outputs-file _outputs.json")
    # Deploy only the application stack from CodeBuild. Deploying the whole app would also redeploy the pipeline
    # (self-mutation), which is unnecessary here and would need broader permissions.
    cdk_deploy = "npx --yes aws-cdk@2 deploy SoundAlongStack " + " ".join(context_flags)

    return codebuild.BuildSpec.from_object(
        {
            "version": "0.2",
            "env": {
                "variables": {
                    "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1",
                    # Avoid buildx attestation manifests that some runtimes reject (mirrors _deploy.ps1).
                    "BUILDX_NO_DEFAULT_ATTESTATIONS": "1",
                    "CDK_DEFAULT_REGION": REGION,
                }
            },
            "phases": {
                "install": {
                    # The repo pins Node 18 (.nvmrc). CodeBuild ships nvm; select 18 explicitly.
                    "runtime-versions": {"nodejs": "18", "python": "3.12"},
                    "commands": [
                        "node --version",
                        "python3 --version",
                        "export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)",
                        "echo \"Deploying to account $CDK_DEFAULT_ACCOUNT in $CDK_DEFAULT_REGION\"",
                    ],
                },
                "pre_build": {
                    "commands": [
                        # 1) Web build -> web/dist
                        "echo '--- web build ---'",
                        "(cd web && npm ci && npm run build)",
                        # 2) API deps + esbuild bundle -> infra/build/api-{lambda,vm}
                        "echo '--- api bundle ---'",
                        "(cd services/api && npm ci)",
                        "python3 -m pip install --upgrade pip",
                        "(cd infra && python3 -m pip install -r requirements-dev.txt)",
                        "(cd infra && python3 bundle_api.py)",
                    ]
                },
                "build": {
                    "commands": [
                        "echo '--- cdk deploy (builds + pushes generator image) ---'",
                        f"(cd infra && {cdk_deploy})",
                    ]
                },
            },
            "artifacts": {
                # Capture the stack outputs so later pipeline stages / humans can read SiteUrl etc.
                "files": ["infra/_outputs.json"],
                "discard-paths": "no",
            },
        }
    )


class PipelineStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, props: PipelineStackProps, **kwargs: object
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- GitHub v2 connection (CodeStar Connections). Created PENDING; authorize once in the console. ---
        github_connection = codestar.CfnConnection(
            self,
            "GitHubConnection",
            connection_name=f"{PROJECT_TAG}-github",
            provider_type="GitHub",
        )

        # --- Artifact bucket (clean teardown in the sandbox) ---
        artifact_bucket = s3.Bucket(
            self,
            "ArtifactBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- CodeBuild project: ARM + privileged so CDK can `docker build` the arm64 generator image ---
        build_project = codebuild.PipelineProject(
            self,
            "BuildDeploy",
            project_name=f"{PROJECT_TAG}-build-deploy",
            build_spec=_buildspec(props),
            environment=codebuild.BuildEnvironment(
                build_image=_ARM_BUILD_IMAGE,
                compute_type=codebuild.ComputeType.LARGE,
                privileged=True,
            ),
            timeout=Duration.hours(1),
        )

        # CodeBuild assumes the CDK bootstrap roles to deploy; grant sts:AssumeRole on them.
        build_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-*"],
            )
        )
        # Reading the caller identity for CDK_DEFAULT_ACCOUNT.
        build_project.add_to_role_policy(
            iam.PolicyStatement(actions=["sts:GetCallerIdentity"], resources=["*"])
        )

        # --- Pipeline ---
        source_output = codepipeline.Artifact("Source")
        build_output = codepipeline.Artifact("BuildOutput")

        source_action = cpactions.CodeStarConnectionsSourceAction(
            action_name="GitHub",
            owner=props.github_owner,
            repo=props.github_repo,
            branch=props.github_branch,
            connection_arn=github_connection.attr_connection_arn,
            output=source_output,
            # V2 pipelines start from an explicit trigger (below), not from the action's DetectChanges flag.
            # DetectChanges alone never started a run here: every execution was a manual StartPipelineExecution.
            trigger_on_push=False,
        )
        build_action = cpactions.CodeBuildAction(
            action_name="BuildAndDeploy",
            project=build_project,
            input=source_output,
            outputs=[build_output],
        )

        codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name=f"{PROJECT_TAG}-pipeline",
            pipeline_type=codepipeline.PipelineType.V2,
            triggers=[
                codepipeline.TriggerProps(
                    provider_type=codepipeline.ProviderType.CODE_STAR_SOURCE_CONNECTION,
                    git_configuration=codepipeline.GitConfiguration(
                        source_action=source_action,
                        push_filter=[
                            codepipeline.GitPushFilter(branches_includes=[props.github_branch]),
                        ],
                    ),
                )
            ],
            artifact_bucket=artifact_bucket,
            stages=[
                codepipeline.StageProps(stage_name="Source", actions=[source_action]),
                codepipeline.StageProps(stage_name="BuildAndDeploy", actions=[build_action]),
            ],
        )
