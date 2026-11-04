#!/usr/bin/env python3
"""CDK entry. Context: alertEmail (optional cost budget), cmsHost = ec2 (default) | lambda,
ttsEngine = kokoro (default) | polly, pollyVoice / pollyVoiceEs / pollyEngine = neural | generative | long-form | standard (only used when ttsEngine=polly),
questionsModel = bedrock:<modelId> (optional, no default), questionsEnabled = true,
translateModel = bedrock:<modelId> | amazon | amazon:informal (optional, no default)."""
from __future__ import annotations

import os
import re

import aws_cdk as cdk

from sound_along.certificate_stack import SiteCertificateStack
from sound_along.config import (
    DEFAULT_POLLY_VOICE,
    DEFAULT_POLLY_VOICE_ES,
    REGION,
    TtsConfig,
    parse_cms_host,
    parse_polly_engine,
    parse_polly_voice,
    parse_questions_enabled,
    parse_reader_insights,
    parse_questions_model,
    parse_site_domain,
    parse_translate_model,
    parse_tts_engine,
)
from sound_along.pipeline_stack import PipelineStack, PipelineStackProps
from sound_along.stack import SoundAlongStack, SoundAlongStackProps

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# GitHub source for the CI/CD pipeline (PipelineStack). Override with -c githubOwner/-c githubRepo/-c githubBranch.
DEFAULT_GITHUB_OWNER = "team49-sound-along"
DEFAULT_GITHUB_REPO = "sound-along"
DEFAULT_GITHUB_BRANCH = "main"


def main() -> None:
    app = cdk.App()
    # The cost budget is optional: some sandbox accounts block the Budgets API, and a failed CreateBudget would roll
    # back the whole stack. Pass -c alertEmail=you@example.com to create it.
    alert_email = app.node.try_get_context("alertEmail")
    if alert_email is not None and not (isinstance(alert_email, str) and EMAIL_PATTERN.match(alert_email)):
        raise ValueError('Invalid CDK context "alertEmail". Use: cdk deploy -c alertEmail=you@example.com')
    cms_host = parse_cms_host(app.node.try_get_context("cmsHost"))
    tts = TtsConfig(
        engine=parse_tts_engine(app.node.try_get_context("ttsEngine")),
        polly_voice=parse_polly_voice(app.node.try_get_context("pollyVoice"), "pollyVoice") or DEFAULT_POLLY_VOICE,
        polly_voice_es=parse_polly_voice(app.node.try_get_context("pollyVoiceEs"), "pollyVoiceEs") or DEFAULT_POLLY_VOICE_ES,
        polly_engine=parse_polly_engine(app.node.try_get_context("pollyEngine")),
    )

    account = os.environ.get("CDK_DEFAULT_ACCOUNT")
    env = cdk.Environment(account=account, region=REGION)

    # Optional custom public domain (-c siteDomain=sound-along.online). When set, the ACM certificate lives in a
    # us-east-1 stack (CloudFront only reads certificates from us-east-1) and the application stack references it
    # across regions. The hosted zone must already exist and be delegated from the registrar.
    site_domain = parse_site_domain(app.node.try_get_context("siteDomain"))
    site_certificate = None
    if site_domain:
        cert_stack = SiteCertificateStack(
            app,
            "SoundAlongCertificate",
            site_domain=site_domain,
            env=cdk.Environment(account=account, region="us-east-1"),
            cross_region_references=True,
        )
        site_certificate = cert_stack.certificate

    SoundAlongStack(
        app,
        "SoundAlongStack",
        props=SoundAlongStackProps(
            alert_email=alert_email, cms_host=cms_host, tts=tts,
            questions_model=parse_questions_model(app.node.try_get_context("questionsModel")),
            questions_enabled=parse_questions_enabled(app.node.try_get_context("questionsEnabled")),
            reader_insights=parse_reader_insights(app.node.try_get_context("readerInsights")),
            translate_model=parse_translate_model(app.node.try_get_context("translateModel")),
            site_domain=site_domain,
            site_certificate=site_certificate,
        ),
        env=env,
        cross_region_references=True,
    )

    # CI/CD pipeline. The build+deploy runs on AWS CodeBuild (ARM, Docker), so the heavy generator image build no
    # longer needs the local machine. tts_engine is only passed through to the pipeline's `cdk deploy` when it is
    # not the default (kokoro), keeping Kokoro the default and Polly an explicit opt-in.
    PipelineStack(
        app,
        "SoundAlongPipeline",
        props=PipelineStackProps(
            github_owner=app.node.try_get_context("githubOwner") or DEFAULT_GITHUB_OWNER,
            github_repo=app.node.try_get_context("githubRepo") or DEFAULT_GITHUB_REPO,
            github_branch=app.node.try_get_context("githubBranch") or DEFAULT_GITHUB_BRANCH,
            tts_engine=tts.engine,
            cms_host=cms_host,
            alert_email=alert_email,
            extra_context=tuple((key, str(app.node.try_get_context(key))) for key in ("pollyVoice", "pollyVoiceEs", "pollyEngine", "translateModel", "siteDomain") if app.node.try_get_context(key) is not None),
        ),
        env=env,
    )

    app.synth()


main()
