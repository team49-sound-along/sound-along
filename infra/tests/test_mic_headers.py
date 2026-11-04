"""The site must not forbid the microphone: "Read aloud with the microphone" calls getUserMedia / SpeechRecognition on the CloudFront page.

A document with no Permissions-Policy header may use the microphone on its own origin (the default allowlist is 'self'). The managed
SecurityHeadersPolicy sets only Referrer-Policy, Strict-Transport-Security, X-Content-Type-Options, X-Frame-Options and X-XSS-Protection.
If a custom response headers policy is ever added, it must either leave Permissions-Policy out or allow microphone=(self).
"""
from __future__ import annotations

from typing import Any

import pytest
from aws_cdk.assertions import Template

from tests.helpers import synth

MANAGED_SECURITY_HEADERS_POLICY_ID = "67f7725c-6f97-4210-82d7-5512b31e9d03"


@pytest.fixture(scope="module", params=["ec2", "lambda"])
def template(request: pytest.FixtureRequest) -> Template:
    return synth(request.param)


def _default_behavior(template: Template) -> dict[str, Any]:
    (dist,) = template.find_resources("AWS::CloudFront::Distribution").values()
    return dist["Properties"]["DistributionConfig"]["DefaultCacheBehavior"]


def _permissions_policy_values(policy: dict[str, Any]) -> list[str]:
    config = policy["Properties"]["ResponseHeadersPolicyConfig"]
    items = config.get("CustomHeadersConfig", {}).get("Items", [])
    return [i["Value"] for i in items if i["Header"].lower() == "permissions-policy"]


def test_default_behavior_uses_headers_that_leave_the_microphone_alone(template: Template) -> None:
    policy_id = _default_behavior(template)["ResponseHeadersPolicyId"]
    if policy_id == MANAGED_SECURITY_HEADERS_POLICY_ID:
        return  # managed policy: no Permissions-Policy and no Content-Security-Policy
    custom = {k: v for k, v in template.find_resources("AWS::CloudFront::ResponseHeadersPolicy").items()}
    ref = policy_id["Ref"] if isinstance(policy_id, dict) else policy_id
    assert ref in custom, "default behavior points at an unknown response headers policy"
    for value in _permissions_policy_values(custom[ref]):
        assert "microphone=(self)" in value.replace(" ", ""), f"Permissions-Policy blocks the microphone: {value}"


def test_no_response_headers_policy_anywhere_blocks_the_microphone(template: Template) -> None:
    for logical_id, policy in template.find_resources("AWS::CloudFront::ResponseHeadersPolicy").items():
        for value in _permissions_policy_values(policy):
            assert "microphone=(self)" in value.replace(" ", ""), f"{logical_id}: {value}"
