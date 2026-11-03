#!/usr/bin/env python3
"""CDK entry. Context: alertEmail (optional cost budget), cmsHost = ec2 (default) | lambda."""
from __future__ import annotations

import os
import re

import aws_cdk as cdk

from sound_along.config import REGION, parse_cms_host
from sound_along.stack import SoundAlongStack, SoundAlongStackProps

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def main() -> None:
    app = cdk.App()
    # The cost budget is optional: some sandbox accounts block the Budgets API, and a failed CreateBudget would roll
    # back the whole stack. Pass -c alertEmail=you@example.com to create it.
    alert_email = app.node.try_get_context("alertEmail")
    if alert_email is not None and not (isinstance(alert_email, str) and EMAIL_PATTERN.match(alert_email)):
        raise ValueError('Invalid CDK context "alertEmail". Use: cdk deploy -c alertEmail=you@example.com')
    cms_host = parse_cms_host(app.node.try_get_context("cmsHost"))

    SoundAlongStack(
        app,
        "SoundAlongStack",
        props=SoundAlongStackProps(alert_email=alert_email, cms_host=cms_host),
        env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=REGION),
    )
    app.synth()


main()
