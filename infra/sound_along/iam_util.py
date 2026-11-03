from __future__ import annotations

from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3


# What the CMS API reads and writes in S3 (nothing else):
#  raw/*                  job inputs and uploaded recordings (write; read for regenerate and "does the recording exist?")
#  raw/ab/manifest.json   the listening-test answer key (read only; outside /data/*, so CloudFront cannot serve it)
API_RAW_PREFIX = "raw/*"
API_MANIFEST_KEY = "raw/ab/manifest.json"


def list_bucket(bucket: s3.IBucket, prefixes: list[str]) -> iam.PolicyStatement:
    """s3:ListBucket limited to the given key prefixes. Without it S3 answers 403 (not 404) for a missing key, which
    would turn "recording not found" and "no stored source to regenerate" into server errors."""
    return iam.PolicyStatement(
        actions=["s3:ListBucket"],
        resources=[bucket.bucket_arn],
        conditions={"StringLike": {"s3:prefix": prefixes}},
    )


def api_s3_policies(bucket: s3.IBucket) -> list[iam.PolicyStatement]:
    """The complete S3 permission set for the CMS API, shared by the Lambda and the VM role."""
    return [
        object_access(bucket, ["s3:PutObject", "s3:GetObject"], API_RAW_PREFIX),
        object_access(bucket, ["s3:GetObject"], API_MANIFEST_KEY),
        list_bucket(bucket, [API_RAW_PREFIX, API_MANIFEST_KEY]),
    ]


def object_access(bucket: s3.IBucket, actions: list[str], prefix: str) -> iam.PolicyStatement:
    """Object-level S3 access only; avoids the s3:Abort* / s3:PutObject* wildcards of bucket.grant_put."""
    return iam.PolicyStatement(actions=actions, resources=[bucket.arn_for_objects(prefix)])
