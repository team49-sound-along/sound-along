from __future__ import annotations

import json

import pytest
from aws_cdk.assertions import Match, Template

from sound_along.config import SourcePaths, parse_cms_host
from tests.helpers import SOURCES, actions_for_roles_starting_with, synth, wildcard_actions


@pytest.fixture(scope="module")
def template() -> Template:
    return synth("ec2")


def test_default_mode_is_ec2() -> None:
    assert parse_cms_host(None) == "ec2"


@pytest.mark.parametrize("bad", ["", "EC2", "fargate", 1])
def test_invalid_cms_host_is_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="cmsHost"):
        parse_cms_host(bad)


def test_instance_type_ami_and_public_ip(template: Template) -> None:
    template.has_resource_properties("AWS::EC2::Instance", {"InstanceType": "t4g.small"})
    ami = json.dumps(template.to_json()["Parameters"])
    assert "al2023-ami" in ami and "arm64" in ami
    launch = template.find_resources("AWS::EC2::LaunchTemplate")
    assert len(launch) == 1
    template.has_resource_properties(
        "AWS::EC2::LaunchTemplate",
        {"LaunchTemplateData": Match.object_like({"MetadataOptions": Match.object_like({"HttpTokens": "required"})})},
    )


def test_root_volume_is_8gb_encrypted_gp3(template: Template) -> None:
    data = next(iter(template.find_resources("AWS::EC2::Instance").values()))["Properties"]
    volumes = data.get("BlockDeviceMappings") or []
    if not volumes:  # CDK moves the mapping into the launch template when IMDSv2 is required
        lt = next(iter(template.find_resources("AWS::EC2::LaunchTemplate").values()))["Properties"]
        volumes = lt["LaunchTemplateData"]["BlockDeviceMappings"]
    assert len(volumes) == 1
    ebs = volumes[0]["Ebs"]
    assert ebs["VolumeSize"] == 8 and ebs["VolumeType"] == "gp3" and ebs["Encrypted"] is True


def test_network_has_one_public_subnet_and_no_nat(template: Template) -> None:
    template.resource_count_is("AWS::EC2::NatGateway", 0)
    template.resource_count_is("AWS::EC2::Subnet", 1)
    template.has_resource_properties("AWS::EC2::Subnet", {"MapPublicIpOnLaunch": True})
    template.resource_count_is("AWS::EC2::EIP", 0)


def test_security_group_has_no_ssh_and_only_cloudfront_on_8080(template: Template) -> None:
    groups = template.find_resources("AWS::EC2::SecurityGroup")
    assert len(groups) == 1
    group = next(iter(groups.values()))["Properties"]
    assert "SecurityGroupIngress" not in group or group["SecurityGroupIngress"] == []
    ingress = list(template.find_resources("AWS::EC2::SecurityGroupIngress").values())
    assert len(ingress) == 1
    props = ingress[0]["Properties"]
    assert (props["IpProtocol"], props["FromPort"], props["ToPort"]) == ("tcp", 8080, 8080)
    assert "CidrIp" not in props
    source = props["SourcePrefixListId"]
    assert "Fn::GetAtt" in source and source["Fn::GetAtt"][1] == "PrefixLists.0.PrefixListId"
    resource_id = source["Fn::GetAtt"][0]
    assert template.find_resources("Custom::AWS")[resource_id]


def test_prefix_list_lookup_is_least_privilege_and_unhardcoded(template: Template) -> None:
    resources = template.find_resources("Custom::AWS")
    assert len(resources) == 1
    custom = next(iter(resources.values()))["Properties"]
    create = json.loads(json.dumps(custom["Create"]))
    text = json.dumps(create)
    assert "describeManagedPrefixLists" in text and "com.amazonaws.global.cloudfront.origin-facing" in text
    assert "pl-" not in text
    policies = [p for p in template.find_resources("AWS::IAM::Policy").values() if "CloudFrontPrefixList" in json.dumps(p)]
    statements = [s for p in policies for s in p["Properties"]["PolicyDocument"]["Statement"]]
    assert [s["Action"] for s in statements] == ["ec2:DescribeManagedPrefixLists"]


def test_instance_role_matches_lambda_grants_without_wildcards(template: Template) -> None:
    actions = actions_for_roles_starting_with(template, "CmsVmInstanceRole")
    assert actions
    assert wildcard_actions(actions) == []
    for needed in ("states:StartExecution", "s3:PutObject", "s3:GetObject", "dynamodb:PutItem", "dynamodb:Query"):
        assert needed in actions, needed
    assert not any(a.startswith(("s3:Delete", "ec2:", "iam:")) for a in actions)
    assert [a for a in actions if a.startswith("s3:List")] == ["s3:ListBucket"]  # prefix-limited, see test_iam_s3.py
    roles = template.find_resources("AWS::IAM::Role")
    ssm = [r for k, r in roles.items() if k.startswith("CmsVmInstanceRole")]
    assert "AmazonSSMManagedInstanceCore" in json.dumps(ssm)


def test_user_data_installs_verified_node_and_systemd_unit(template: Template) -> None:
    instance = next(iter(template.find_resources("AWS::EC2::Instance").values()))["Properties"]
    user_data = json.dumps(instance["UserData"])
    assert "node-v18.20.8-linux-arm64.tar.xz" in user_data
    assert "224e569dbe7b0ea4628ce383d9d482494b57ee040566583f1c54072c86d1116b" in user_data and "sha256sum -c" in user_data
    for key in ("BUCKET", "TABLE_NAME", "STATE_MACHINE_ARN", "GENERATION_ENABLED", "GENERATE_PER_MINUTE",
                "MAX_CONCURRENT_JOBS", "PORT=8080", "AWS_REGION=us-west-2"):
        assert f"Environment={key}" in user_data.replace("\\n", "\n") or key in user_data
    assert "Restart=always" in user_data and "serverVm.js" in user_data and "User=soundalong" in user_data
    assert "aws s3 cp" in user_data


def test_cloudfront_api_origin_is_the_instance_on_8080(template: Template) -> None:
    dist = next(iter(template.find_resources("AWS::CloudFront::Distribution").values()))["Properties"]["DistributionConfig"]
    behavior = next(b for b in dist["CacheBehaviors"] if b["PathPattern"] == "/api/*")
    origin = next(o for o in dist["Origins"] if o["Id"] == behavior["TargetOriginId"])
    assert origin["DomainName"]["Fn::GetAtt"][1] == "PublicDnsName"
    assert origin["DomainName"]["Fn::GetAtt"][0].startswith("CmsVmInstance")
    config = origin["CustomOriginConfig"]
    assert config["HTTPPort"] == 8080 and config["OriginProtocolPolicy"] == "http-only"
    assert behavior["ViewerProtocolPolicy"] == "https-only"
    assert behavior["AllowedMethods"] == ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"]


def test_no_function_url_or_api_lambda_and_one_oac(template: Template) -> None:
    template.resource_count_is("AWS::Lambda::Url", 0)
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)  # S3 only
    runtimes = [f["Properties"].get("Runtime") for f in template.find_resources("AWS::Lambda::Function").values()]
    assert "nodejs18.x" not in runtimes


def test_outputs_for_ssm_access(template: Template) -> None:
    outputs = template.to_json()["Outputs"]
    assert "CmsInstanceId" in outputs
    assert "aws ssm start-session --target" in json.dumps(outputs["CmsSessionCommand"])


def test_missing_vm_bundle_gives_actionable_error(tmp_path) -> None:
    sources = SourcePaths(
        lambda_dir=SOURCES.lambda_dir, vm_dir=tmp_path / "nope", generator_dir=SOURCES.generator_dir, web_dist=SOURCES.web_dist,
        questions_dir=SOURCES.questions_dir,
    )
    with pytest.raises(FileNotFoundError, match="python bundle_api.py"):
        synth("ec2", sources=sources)
