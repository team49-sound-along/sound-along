from __future__ import annotations

from collections.abc import Sequence

from aws_cdk import Duration
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .config import API_PORT


def lambda_api_origin(api_function: lambda_.Function) -> cloudfront.IOrigin:
    """cmsHost=lambda: Function URL (AuthType AWS_IAM) invoked by CloudFront through OAC.

    OAC signs requests with SigV4. Signing a POST/PATCH body requires the VIEWER to send `x-amz-content-sha256`
    (hex SHA-256 of the body): CloudFront cannot compute it and a CloudFront Function cannot read the body, so the
    web client must add the header (see infra/README.md). AllViewerExceptHostHeader forwards that header; Host must
    be excluded or SigV4 breaks.
    """
    url = api_function.add_function_url(auth_type=lambda_.FunctionUrlAuthType.AWS_IAM)
    return origins.FunctionUrlOrigin.with_origin_access_control(url)


def vm_api_origin(instance_dns_name: str) -> cloudfront.IOrigin:
    """cmsHost=ec2: plain HTTP to the instance on 8080. The security group admits only CloudFront's prefix list."""
    return origins.HttpOrigin(
        instance_dns_name,
        protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        http_port=API_PORT,
    )


def lookup_hosted_zone(scope: Construct, construct_id: str, domain_name: str) -> route53.IHostedZone:
    """Find the public hosted zone that is authoritative for `domain_name` (the apex). The zone must already exist;
    it is created once (the domain is registered at an external registrar and its nameservers delegated to it)."""
    return route53.HostedZone.from_lookup(scope, construct_id, domain_name=domain_name)


def create_site_certificate(
    scope: Construct, construct_id: str, *, domain_name: str, hosted_zone: route53.IHostedZone
) -> acm.Certificate:
    """DNS-validated ACM certificate for the site domain. CloudFront reads certificates only from us-east-1, so the
    scope passed here must belong to a us-east-1 stack."""
    return acm.Certificate(
        scope,
        construct_id,
        domain_name=domain_name,
        validation=acm.CertificateValidation.from_dns(hosted_zone),
    )


def create_alias_records(
    scope: Construct, *, domain_name: str, hosted_zone: route53.IHostedZone, distribution: cloudfront.IDistribution
) -> None:
    """Point the apex domain at the CloudFront distribution with Route 53 alias A and AAAA records."""
    target = route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(distribution))
    route53.ARecord(scope, "SiteAliasA", zone=hosted_zone, record_name=domain_name, target=target)
    route53.AaaaRecord(scope, "SiteAliasAAAA", zone=hosted_zone, record_name=domain_name, target=target)


def _audio_cache_policy(scope: Construct) -> cloudfront.CachePolicy:
    """Audio cache policy. CloudFront forwards the viewer's Range header to the origin and caches partial responses
    on its own, so Range does NOT need to be in the cache key (adding it would fragment the cache). Headers, cookies
    and query strings are not forwarded: an empty key means one cached object per file. Files are keyed by immutable
    UUIDs, hence the long TTLs. Compression is off because MP3 is already compressed and gzip would break byte-range
    math."""
    return cloudfront.CachePolicy(
        scope,
        "AudioCachePolicy",
        comment="Audio and timing files; Range requests handled natively by CloudFront",
        default_ttl=Duration.days(1),
        min_ttl=Duration.seconds(0),
        max_ttl=Duration.days(365),
        header_behavior=cloudfront.CacheHeaderBehavior.none(),
        cookie_behavior=cloudfront.CacheCookieBehavior.none(),
        query_string_behavior=cloudfront.CacheQueryStringBehavior.none(),
        enable_accept_encoding_gzip=False,
        enable_accept_encoding_brotli=False,
    )


def create_site_distribution(
    scope: Construct,
    *,
    bucket: s3.IBucket,
    api_origin: cloudfront.IOrigin,
    domain_names: Sequence[str] | None = None,
    certificate: acm.ICertificate | None = None,
) -> cloudfront.Distribution:
    """Create the site distribution. When `domain_names` and `certificate` are given, CloudFront also answers for
    those names over HTTPS using the ACM certificate (which must live in us-east-1). Without them it serves only its
    default *.cloudfront.net domain."""
    oac = cloudfront.S3OriginAccessControl(scope, "BucketOac")
    app_origin = origins.S3BucketOrigin.with_origin_access_control(
        bucket, origin_path="/app", origin_access_control=oac
    )
    data_origin = origins.S3BucketOrigin.with_origin_access_control(bucket, origin_access_control=oac)

    return cloudfront.Distribution(
        scope,
        "Distribution",
        comment="Sound Along",
        default_root_object="index.html",
        price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        domain_names=list(domain_names) if domain_names else None,
        certificate=certificate,
        default_behavior=cloudfront.BehaviorOptions(
            origin=app_origin,
            compress=True,
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        ),
        additional_behaviors={
            "/data/*": cloudfront.BehaviorOptions(
                origin=data_origin,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=_audio_cache_policy(scope),
            ),
            "/api/*": cloudfront.BehaviorOptions(
                origin=api_origin,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            ),
        },
    )
