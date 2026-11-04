from __future__ import annotations

from pathlib import Path
from typing import Any

import aws_cdk as cdk
from aws_cdk.assertions import Template

from sound_along.config import SourcePaths
from sound_along.stack import SoundAlongStack, SoundAlongStackProps

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = SourcePaths(
    lambda_dir=FIXTURES / "api-lambda",
    vm_dir=FIXTURES / "api-vm",
    generator_dir=FIXTURES / "generator",
    web_dist=FIXTURES / "web-dist",
    questions_dir=FIXTURES / "questions",
)


def synth(cms_host: str = "ec2", alert_email: str | None = "test@example.com", sources: SourcePaths = SOURCES, questions_model: str | None = None, questions_enabled: bool = False, translate_model: str | None = None) -> Template:
    app = cdk.App()
    stack = SoundAlongStack(
        app,
        "TestStack",
        props=SoundAlongStackProps(alert_email=alert_email, cms_host=cms_host, sources=sources, questions_model=questions_model, questions_enabled=questions_enabled, translate_model=translate_model),
        env=cdk.Environment(region="us-west-2"),
    )
    return Template.from_stack(stack)


def actions_for_roles_starting_with(template: Template, prefix: str) -> list[str]:
    """Every IAM action granted by inline policies attached to roles whose logical id starts with `prefix`."""
    actions: list[str] = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        props: dict[str, Any] = policy["Properties"]
        if not any(role["Ref"].startswith(prefix) for role in props["Roles"]):
            continue
        for statement in props["PolicyDocument"]["Statement"]:
            raw = statement["Action"]
            actions.extend(raw if isinstance(raw, list) else [raw])
    return actions


def wildcard_actions(actions: list[str]) -> list[str]:
    return [a for a in actions if a == "*" or a.endswith("*")]
