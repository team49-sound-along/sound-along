"""Assertions that hold in both cmsHost modes (ported from the TypeScript stack tests)."""
from __future__ import annotations

import json
import re

import pytest
from aws_cdk.assertions import Match, Template

from tests.helpers import synth


@pytest.fixture(scope="module", params=["ec2", "lambda"])
def template(request: pytest.FixtureRequest) -> Template:
    return synth(request.param)


def test_private_encrypted_ssl_only_bucket_with_raw_expiry(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True,
            },
            "BucketEncryption": {"ServerSideEncryptionConfiguration": Match.any_value()},
            "LifecycleConfiguration": {
                "Rules": [Match.object_like({"Prefix": "raw/", "ExpirationInDays": 7, "Status": "Enabled"})]
            },
        },
    )
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [Match.object_like({"Effect": "Deny", "Condition": {"Bool": {"aws:SecureTransport": "false"}}})]
                )
            }
        },
    )


def test_distribution_behaviors(template: Template) -> None:
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": {
                "DefaultRootObject": "index.html",
                "DefaultCacheBehavior": Match.object_like({"ViewerProtocolPolicy": "redirect-to-https", "Compress": True}),
                "CacheBehaviors": [
                    Match.object_like({"PathPattern": "/data/*", "AllowedMethods": ["GET", "HEAD"]}),
                    Match.object_like(
                        {
                            "PathPattern": "/api/*",
                            "AllowedMethods": ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"],
                            "ViewerProtocolPolicy": "https-only",
                        }
                    ),
                ],
                "Origins": Match.array_with([Match.object_like({"OriginPath": "/app"})]),
            }
        },
    )


def test_generator_container_lambda(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "PackageType": "Image",
            "Architectures": ["arm64"],
            "MemorySize": 4096,
            "Timeout": 900,  # the Lambda maximum: the longest text can need minutes to translate and narrate
            "ReservedConcurrentExecutions": 2,
            "Environment": {"Variables": {"BUCKET": Match.any_value(), "TABLE_NAME": Match.any_value()}},
        },
    )


def test_standard_state_machine_with_one_retrying_task(template: Template) -> None:
    template.has_resource_properties(
        "AWS::StepFunctions::StateMachine",
        {"StateMachineName": "GenerateStateMachine", "StateMachineType": "STANDARD", "DefinitionString": Match.any_value()},
    )
    machines = list(template.find_resources("AWS::StepFunctions::StateMachine").values())
    definition = json.dumps(machines[0]["Properties"]["DefinitionString"])
    assert "Retry" in definition
    assert re.search(r"MaxAttempts\D+1\b", definition)
    assert "States.TaskFailed" not in definition
    assert "Payload.$" in definition
    assert re.search(r"TimeoutSeconds\D+28800\b", definition)


def test_on_demand_table_with_ttl(template: Template) -> None:
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        },
    )


def test_budget_alerts_at_25_50_80(template: Template) -> None:
    budgets = list(template.find_resources("AWS::Budgets::Budget").values())
    assert len(budgets) == 1
    props = budgets[0]["Properties"]
    assert props["Budget"]["BudgetLimit"]["Amount"] == 500
    notifications = props["NotificationsWithSubscribers"]
    assert [n["Notification"]["Threshold"] for n in notifications] == [25, 50, 80]
    assert all(n["Notification"]["NotificationType"] == "ACTUAL" for n in notifications)


def test_web_deployment_and_outputs(template: Template) -> None:
    template.resource_count_is("Custom::CDKBucketDeployment", 1)
    outputs = template.to_json()["Outputs"]
    for name in ("SiteUrl", "BucketName", "TableName", "StateMachineArn", "CmsHost"):
        assert name in outputs, f"missing output {name}"


def test_no_budget_without_alert_email() -> None:
    """A sandbox that blocks the Budgets API must not fail the deploy."""
    for mode in ("ec2", "lambda"):
        assert synth(mode, alert_email=None).find_resources("AWS::Budgets::Budget") == {}
