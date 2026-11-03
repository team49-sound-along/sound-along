from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import Annotations, CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from .budget import CostBudget
from .cdn import create_site_distribution, lambda_api_origin, vm_api_origin
from .cms_vm import CmsVm, CmsVmProps
from .config import (
    CMS_HOST_EC2,
    CMS_HOST_LAMBDA,
    DEFAULT_CMS_HOST,
    PROJECT_TAG,
    SourcePaths,
    default_source_paths,
    parse_cms_host,
    require_bundle,
)
from .functions import (
    ApiFunctionProps,
    GeneratorFunctionProps,
    create_api_function,
    create_generator_function,
)
from .pipeline import create_state_machine


@dataclass(frozen=True)
class SoundAlongStackProps:
    """`alert_email` creates the cost budget (optional: sandboxes may block the Budgets API)."""

    alert_email: str | None = None
    cms_host: str = DEFAULT_CMS_HOST
    sources: SourcePaths | None = None


class SoundAlongStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, props: SoundAlongStackProps, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cms_host = parse_cms_host(props.cms_host)
        sources = props.sources or default_source_paths()
        Tags.of(self).add("project", PROJECT_TAG)

        bucket = s3.Bucket(
            self,
            "Bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[s3.LifecycleRule(prefix="raw/", expiration=Duration.days(7))],
        )
        table = dynamodb.Table(
            self,
            "Table",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        generator = create_generator_function(
            self, GeneratorFunctionProps(generator_dir=sources.generator_dir, bucket=bucket, table=table)
        )
        state_machine = create_state_machine(self, generator)

        if cms_host == CMS_HOST_EC2:
            vm = CmsVm(
                self,
                "CmsVm",
                props=CmsVmProps(
                    vm_dir=require_bundle(sources.vm_dir, "VM API bundle"),
                    bucket=bucket,
                    table=table,
                    state_machine=state_machine,
                ),
            )
            api_origin = vm_api_origin(vm.public_dns_name)
        else:
            api = create_api_function(
                self,
                ApiFunctionProps(
                    code_dir=require_bundle(sources.lambda_dir, "Lambda API bundle"), bucket=bucket, table=table
                ),
            )
            api.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)
            state_machine.grant_start_execution(api)
            api_origin = lambda_api_origin(api)

        distribution = create_site_distribution(self, bucket=bucket, api_origin=api_origin)
        self._deploy_web_app(sources.web_dist, bucket, distribution)

        if props.alert_email:
            CostBudget(self, "CostBudget", alert_email=props.alert_email)
        else:
            Annotations.of(self).add_info("No cost budget created. Pass -c alertEmail=you@example.com to add one.")

        CfnOutput(self, "SiteUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "TableName", value=table.table_name)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "CmsHost", value=cms_host)

    def _deploy_web_app(self, web_dist: Path, bucket: s3.IBucket, distribution: cloudfront.IDistribution) -> None:
        if not web_dist.exists():
            Annotations.of(self).add_warning(
                f'Web build not found at {web_dist}; skipping BucketDeployment. Run "npm run build" in web/ and synth again.'
            )
            return
        s3deploy.BucketDeployment(
            self,
            "WebDeployment",
            sources=[s3deploy.Source.asset(str(web_dist))],
            destination_bucket=bucket,
            destination_key_prefix="app",
            distribution=distribution,
            distribution_paths=["/*"],
            memory_limit=512,
        )
