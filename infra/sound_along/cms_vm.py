"""cmsHost=ec2: the CMS API on one small EC2 instance behind CloudFront (no NAT, no SSH, access via SSM)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_assets as s3_assets
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import custom_resources as cr
from constructs import Construct

from .config import API_ENV_DEFAULTS, API_PORT, REGION
from .iam_util import api_s3_policies, object_access

CLOUDFRONT_PREFIX_LIST_NAME = "com.amazonaws.global.cloudfront.origin-facing"
NODE_VERSION = "18.20.8"
NODE_ARCHIVE = f"node-v{NODE_VERSION}-linux-arm64.tar.xz"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ARCHIVE}"
NODE_SHA256 = "224e569dbe7b0ea4628ce383d9d482494b57ee040566583f1c54072c86d1116b"
APP_DIR = "/opt/sound-along"
SERVICE_USER = "soundalong"
INSTANCE_TYPE = "t4g.small"


@dataclass(frozen=True)
class CmsVmProps:
    vm_dir: Path
    bucket: s3.IBucket
    table: dynamodb.ITable
    state_machine: sfn.IStateMachine
    reader_insights: bool = False
    default_tts_engine: str = "polly"  # the narration engine the Settings screen starts with


def _unit_file(env: dict[str, str]) -> list[str]:
    lines = [
        "[Unit]",
        "Description=Sound Along CMS API",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        f"User={SERVICE_USER}",
        f"WorkingDirectory={APP_DIR}/src",
        *[f"Environment={key}={value}" for key, value in env.items()],
        "ExecStart=/opt/node/bin/node serverVm.js",
        "Restart=always",
        "RestartSec=5",
        "NoNewPrivileges=true",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ]
    return lines


def build_user_data_commands(*, asset_url: str, env: dict[str, str]) -> list[str]:
    """First-boot script (cloud-init runs it once, as root). Any failed step aborts it, so the service never starts
    on a half-installed box."""
    return [
        "set -euo pipefail",
        "",
        "# 1. Node.js from the official tarball; refuse to install it unless the checksum matches.",
        "command -v xz >/dev/null || dnf install -y xz",
        f"curl -fsSL -o /tmp/{NODE_ARCHIVE} {NODE_URL}",
        f'echo "{NODE_SHA256}  /tmp/{NODE_ARCHIVE}" | sha256sum -c -',
        f"mkdir -p /opt/node && tar -xJf /tmp/{NODE_ARCHIVE} -C /opt/node --strip-components=1",
        "",
        "# 2. App bundle from the CDK asset bucket (the instance role may read exactly this object).",
        f"useradd --system --no-create-home --shell /sbin/nologin {SERVICE_USER}",
        f"mkdir -p {APP_DIR}",
        f"aws s3 cp {asset_url} /tmp/app.zip --region {REGION}",
        f"python3 -m zipfile -e /tmp/app.zip {APP_DIR}",
        "",
        "# 3. systemd unit: non-root, restarts on crash and on reboot.",
        "cat > /etc/systemd/system/sound-along.service <<'EOF'",
        *_unit_file(env),
        "EOF",
        "systemctl daemon-reload",
        "systemctl enable --now sound-along.service",
    ]


class CmsVm(Construct):
    """VPC, security group, instance role and the instance itself."""

    def __init__(self, scope: Construct, construct_id: str, *, props: CmsVmProps) -> None:
        super().__init__(scope, construct_id)
        vpc = self._create_vpc()
        security_group = self._create_security_group(vpc)
        asset = s3_assets.Asset(self, "AppBundle", path=str(props.vm_dir))
        role = self._create_role(props, asset)

        env = {
            "BUCKET": props.bucket.bucket_name,
            "TABLE_NAME": props.table.table_name,
            "STATE_MACHINE_ARN": props.state_machine.state_machine_arn,
            **API_ENV_DEFAULTS,
            "READER_INSIGHTS": "true" if props.reader_insights else "false",
            "DEFAULT_TTS_ENGINE": props.default_tts_engine,
            "PORT": str(API_PORT),
            "AWS_REGION": REGION,
        }
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(*build_user_data_commands(asset_url=asset.s3_object_url, env=env))

        self.instance = ec2.Instance(
            self,
            "Instance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType(INSTANCE_TYPE),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=ec2.AmazonLinuxCpuType.ARM_64),
            security_group=security_group,
            role=role,
            require_imdsv2=True,
            associate_public_ip_address=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(8, volume_type=ec2.EbsDeviceVolumeType.GP3, encrypted=True),
                )
            ],
            user_data=user_data,
            # A new app bundle changes the user data; replace the instance so the new bundle is installed.
            user_data_causes_replacement=True,
        )

        stack = Stack.of(self)
        CfnOutput(stack, "CmsInstanceId", value=self.instance.instance_id)
        CfnOutput(
            stack,
            "CmsSessionCommand",
            value=f"aws ssm start-session --target {self.instance.instance_id} --region {REGION}",
        )

    @property
    def public_dns_name(self) -> str:
        return self.instance.instance_public_dns_name

    def _create_vpc(self) -> ec2.Vpc:
        # One AZ, one public subnet, no NAT gateway: the instance has its own public IPv4 and egress via the IGW.
        return ec2.Vpc(
            self,
            "Vpc",
            max_azs=1,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24)
            ],
        )

    def _create_security_group(self, vpc: ec2.IVpc) -> ec2.SecurityGroup:
        security_group = ec2.SecurityGroup(
            self, "SecurityGroup", vpc=vpc, description="CMS API: CloudFront only, no SSH", allow_all_outbound=True
        )
        prefix_list_id = self._cloudfront_prefix_list_id()
        # Only CloudFront origin-facing addresses may reach the API port. No port 22 rule: use SSM Session Manager.
        security_group.add_ingress_rule(
            ec2.Peer.prefix_list(prefix_list_id), ec2.Port.tcp(API_PORT), "CloudFront origin-facing"
        )
        return security_group

    def _cloudfront_prefix_list_id(self) -> str:
        """Look the managed prefix list id up at deploy time so no id is hardcoded."""
        lookup = cr.AwsCustomResource(
            self,
            "CloudFrontPrefixList",
            on_update=cr.AwsSdkCall(
                service="EC2",
                action="describeManagedPrefixLists",
                parameters={"Filters": [{"Name": "prefix-list-name", "Values": [CLOUDFRONT_PREFIX_LIST_NAME]}]},
                physical_resource_id=cr.PhysicalResourceId.of(CLOUDFRONT_PREFIX_LIST_NAME),
                region=REGION,
            ),
            # ec2:Describe* actions do not support resource-level permissions, so "*" is the only valid resource.
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [iam.PolicyStatement(actions=["ec2:DescribeManagedPrefixLists"], resources=["*"])]
            ),
            install_latest_aws_sdk=False,
        )
        return lookup.get_response_field("PrefixLists.0.PrefixListId")

    def _create_role(self, props: CmsVmProps, asset: s3_assets.Asset) -> iam.Role:
        """Same grants as the API Lambda (plus S3 read of raw/* for regenerate and the app bundle), nothing wider."""
        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")],
        )
        props.table.grant_read_write_data(role)
        props.state_machine.grant_start_execution(role)
        for statement in api_s3_policies(props.bucket):
            role.add_to_policy(statement)
        role.add_to_policy(object_access(asset.bucket, ["s3:GetObject"], asset.s3_object_key))
        return role
