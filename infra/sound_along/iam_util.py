from __future__ import annotations

from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3


# What the CMS API reads and writes in S3 (nothing else):
#  raw/*                  job inputs and uploaded recordings (write; read for regenerate and "does the recording exist?")
#  raw/ab/manifest.json   the listening-test answer key (read only; outside /data/*, so CloudFront cannot serve it)
API_RAW_PREFIX = "raw/*"
API_MANIFEST_KEY = "raw/ab/manifest.json"
#  data/*.questions.json  the approved practice questions (write only). A teacher publishes them from the app; drafts stay under raw/questions/*
#                         (covered by raw/*) and are never written to data/. It cannot overwrite audio, timing or any other data file.
API_QUESTIONS_KEY = "data/*.questions.json"
#  data/*.timing.json     the passages' word lists (read only). The anonymous read-aloud results name a word by its position; the API looks the
#                         word up here, so word text is never taken from a browser. Audio, cards and every other data file stay unreadable.
API_TIMING_KEY = "data/*.timing.json"
#  data/<id>.<suffix>     a teacher deletes a passage from the Library (delete only): exactly the files the generator writes per passage. The index and
#                         the shared, content-hashed pictures do not match these names. Same list as PASSAGE_FILE_SUFFIXES in services/api/src/catalog.js.
API_PASSAGE_FILE_KEYS = tuple(f"data/*.{suffix}" for suffix in ("timing.json", "mp3", "soundalong.json", "cards.json", "questions.json", "pcm.npy"))
#  data/index.json        the Library list (write only), published again after a delete, from the PASSAGE items that are left (as the generator does).
API_INDEX_KEY = "data/index.json"


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
        object_access(bucket, ["s3:PutObject"], API_QUESTIONS_KEY),
        object_access(bucket, ["s3:GetObject"], API_TIMING_KEY),
        iam.PolicyStatement(actions=["s3:DeleteObject"], resources=[bucket.arn_for_objects(key) for key in API_PASSAGE_FILE_KEYS]),
        object_access(bucket, ["s3:PutObject"], API_INDEX_KEY),
        list_bucket(bucket, [API_RAW_PREFIX, API_MANIFEST_KEY, API_TIMING_KEY]),
    ]


def object_access(bucket: s3.IBucket, actions: list[str], prefix: str) -> iam.PolicyStatement:
    """Object-level S3 access only; avoids the s3:Abort* / s3:PutObject* wildcards of bucket.grant_put."""
    return iam.PolicyStatement(actions=actions, resources=[bucket.arn_for_objects(prefix)])


def polly_synthesize() -> iam.PolicyStatement:
    """polly:SynthesizeSpeech only (no list/describe). Resource is * because Polly voices are not ARN-scoped.
    Granted to the generator role only when ttsEngine=polly."""
    return iam.PolicyStatement(actions=["polly:SynthesizeSpeech"], resources=["*"])
