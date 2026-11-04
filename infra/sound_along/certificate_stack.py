"""A tiny stack that holds the site's ACM certificate in us-east-1.

CloudFront reads certificates only from us-east-1, but the application stack runs in us-west-2. This stack is created
in us-east-1 so the certificate lives in the right region; the application stack references it across regions
(both stacks set cross_region_references=True). It is created only when a custom site domain is configured.
"""
from __future__ import annotations

from aws_cdk import Stack, Tags
from aws_cdk import aws_certificatemanager as acm
from constructs import Construct

from .cdn import create_site_certificate, lookup_hosted_zone
from .config import PROJECT_TAG


class SiteCertificateStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, site_domain: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Tags.of(self).add("project", PROJECT_TAG)
        hosted_zone = lookup_hosted_zone(self, "SiteHostedZone", site_domain)
        self.certificate: acm.Certificate = create_site_certificate(
            self, "SiteCertificate", domain_name=site_domain, hosted_zone=hosted_zone
        )
