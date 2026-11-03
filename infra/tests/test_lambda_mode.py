from __future__ import annotations

import pytest
from aws_cdk.assertions import Match, Template

from sound_along.config import SourcePaths
from tests.helpers import SOURCES, actions_for_roles_starting_with, synth, wildcard_actions


@pytest.fixture(scope="module")
def template() -> Template:
    return synth("lambda")


def test_api_lambda_runs_node_18(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Runtime": "nodejs18.x",
            "Handler": "src/index.handler",
            "Architectures": ["arm64"],
            "MemorySize": 512,
            "Timeout": 30,
            "ReservedConcurrentExecutions": 5,
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "GENERATION_ENABLED": "true",
                        "GENERATE_PER_MINUTE": "3",
                        "MAX_CONCURRENT_JOBS": "2",
                        "BUCKET": Match.any_value(),
                        "TABLE_NAME": Match.any_value(),
                        "STATE_MACHINE_ARN": Match.any_value(),
                    }
                )
            },
        },
    )


def test_function_url_with_oac_and_no_instance(template: Template) -> None:
    template.has_resource_properties("AWS::Lambda::Url", {"AuthType": "AWS_IAM"})
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 2)  # S3 + Lambda URL
    for kind in ("AWS::EC2::Instance", "AWS::EC2::VPC", "AWS::EC2::SecurityGroup", "AWS::EC2::LaunchTemplate"):
        template.resource_count_is(kind, 0)


def test_no_wildcard_actions_on_workload_roles(template: Template) -> None:
    for prefix in ("ApiFunctionServiceRole", "GeneratorFunctionServiceRole", "GenerateStateMachineRole"):
        actions = actions_for_roles_starting_with(template, prefix)
        assert actions, f"no policy found for {prefix}"
        assert wildcard_actions(actions) == [], f"{prefix} has wildcard actions"


def test_api_lambda_s3_access_is_limited_to_raw_inputs_the_manifest_and_a_prefix_limited_list(template: Template) -> None:
    api = actions_for_roles_starting_with(template, "ApiFunctionServiceRole")
    assert "s3:PutObject" in api and "s3:GetObject" in api and "states:StartExecution" in api
    s3_actions = {a for a in api if a.startswith("s3:")}
    assert s3_actions == {"s3:PutObject", "s3:GetObject", "s3:ListBucket"}, s3_actions


def test_missing_bundle_gives_actionable_error(tmp_path) -> None:
    sources = SourcePaths(
        lambda_dir=tmp_path / "nope", vm_dir=SOURCES.vm_dir, generator_dir=SOURCES.generator_dir, web_dist=SOURCES.web_dist,
        questions_dir=SOURCES.questions_dir,
    )
    with pytest.raises(FileNotFoundError, match="python bundle_api.py"):
        synth("lambda", sources=sources)
