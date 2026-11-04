"""Builds the Sound Along architecture diagram (SVG, plus PNG through headless Edge or Chrome).

The layout mirrors infra/sound_along/*.py. Icons in ./icons come from the official AWS Architecture Icons package
(https://aws.amazon.com/architecture/icons/, 07-31-2026 release) and are embedded so the SVG is self-contained.

    python build_diagram.py            # writes sound-along-architecture.svg and .png next to this file
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
SVG_OUT = HERE / "sound-along-architecture.svg"
PNG_OUT = HERE / "sound-along-architecture.png"
WIDTH, HEIGHT = 1820, 1590
DY = 150                      # everything inside the Region (and below) is drawn this far down, under the global / us-east-1 strip
DATA_Y, DATA_H = 905, 190     # Data and Operations row (coordinates before the DY shift)
CICD_Y = DATA_Y + DATA_H + 18
FONT = "'Amazon Ember', 'Segoe UI', Helvetica, Arial, sans-serif"

USER = "#232F3E"      # user traffic
SERVICE = "#1F6FD1"   # service and data flow
DEPLOY = "#E07B00"    # deployment flow

out: list[str] = []
_icon_cache: dict[str, str] = {}


def icon_uri(name: str) -> str:
    if name not in _icon_cache:
        data = base64.b64encode((ICONS / f"{name}.svg").read_bytes()).decode()
        _icon_cache[name] = f"data:image/svg+xml;base64,{data}"
    return _icon_cache[name]


def icon(name: str, x: float, y: float, size: float = 40) -> None:
    out.append(f'<image href="{icon_uri(name)}" x="{x}" y="{y}" width="{size}" height="{size}"/>')


def text(x, y, s, size=12, weight="normal", color="#232F3E", anchor="start", italic=False, rotate=None, halo=False) -> None:
    style = "font-style:italic;" if italic else ""
    extra = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    if halo:
        extra += ' stroke="#ffffff" stroke-width="4" paint-order="stroke" stroke-linejoin="round"'
    out.append(
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}" style="{style}"{extra}>{escape(s)}</text>'
    )


def rect(x, y, w, h, fill="#ffffff", stroke="#d5dbe3", width=1.0, dash=None, rx=8) -> None:
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{d}/>')


def container(x, y, w, h, label, *, fill, stroke, dash=None, icon_name=None, sub=None, width=1.6, label_color=None) -> None:
    rect(x, y, w, h, fill=fill, stroke=stroke, dash=dash, width=width, rx=10)
    tx = x + 12
    if icon_name:
        icon(icon_name, x + 1, y + 1, 30)
        tx = x + 40
    text(tx, y + 21, label, size=14, weight="bold", color=label_color or "#16325c")
    if sub:
        text(tx, y + 37, sub, size=11, color="#4a5b70")


def card(x, y, w, h, icon_name, title, lines=(), *, icon_size=40, title_size=13, line_size=11.5, fill="#ffffff") -> None:
    rect(x, y, w, h, fill=fill, stroke="#cfd8e3", rx=8)
    icon(icon_name, x + 10, y + 10, icon_size)
    tx = x + icon_size + 20
    text(tx, y + 24, title, size=title_size, weight="bold")
    for i, line in enumerate(lines):
        text(tx, y + 24 + 16 * (i + 1), line, size=line_size, color="#3d4b5c")


def arrow(points, color=SERVICE, dash=None, width=1.8, label=None, label_at=None, label_anchor="middle", label_rotate=None) -> None:
    marker = {USER: "a-user", SERVICE: "a-service", DEPLOY: "a-deploy"}[color]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{px},{py}" for px, py in points)
    out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{d} marker-end="url(#{marker})"/>')
    if label:
        lx, ly = label_at
        text(lx, ly, label, size=11, weight="bold", color=color, anchor=label_anchor, rotate=label_rotate, halo=True)


def defs() -> None:
    out.append("<defs>")
    for mid, color in (("a-user", USER), ("a-service", SERVICE), ("a-deploy", DEPLOY)):
        out.append(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
        )
    out.append(
        '<linearGradient id="hdr" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/>'
        '<stop offset="1" stop-color="#dcebfb"/></linearGradient>'
    )
    out.append("</defs>")


def header() -> None:
    out.append(f'<rect x="0" y="0" width="{WIDTH}" height="78" fill="url(#hdr)"/>')
    out.append(f'<line x1="0" y1="78" x2="{WIDTH}" y2="78" stroke="#c9d6e6"/>')
    icon("grp-cloud", 22, 14, 50)
    out.append('<line x1="86" y1="14" x2="86" y2="64" stroke="#c9d6e6"/>')
    text(102, 42, "Sound Along \u2013 Application Infrastructure Diagram", size=28, weight="bold", color="#16325c")
    text(104, 64, "Read-along audio for learners  \u2022  Serverless generation  \u2022  Least privilege  \u2022  Cost bounded",
         size=13, color="#4a6a8f")
    text(1800, 36, "Region us-west-2  \u2022  AWS CDK (Python)", size=14, weight="bold", color="#16325c", anchor="end")
    text(1800, 56, "Stacks: SoundAlongStack + SoundAlongPipeline (+ SoundAlongCertificate, optional)", size=12, color="#4a6a8f", anchor="end")


def actors() -> None:
    card(430, 92, 290, 68, "users", "Learners & Teachers", ["Browser: read-along player", "audio with word-by-word timing"])
    card(780, 92, 290, 68, "client", "Content Authors", ["Browser: CMS pages", "upload, generate, review cards"])
    # Read-aloud speech recognition never touches AWS.
    rect(30, 92, 382, 74, fill="#fffdf7", stroke="#8a96a3", dash="6 4", rx=8)
    text(42, 111, "Read-aloud speech stays in the browser", size=12, weight="bold")
    for i, line in enumerate((
        "Uses the browser's own speech recognition: the audio goes to",
        "the browser maker's speech service, never to our AWS account,",
        "and is never stored. No AWS speech service is used.",
    )):
        text(42, 128 + i * 15, line, size=11, color="#3d4b5c")
    out.append('<line x1="412" y1="126" x2="430" y2="126" stroke="#8a96a3" stroke-width="1.4" stroke-dasharray="3 3"/>')


def aws_cloud() -> None:
    container(30, 180, 1530, CICD_Y + 170 + 15 + 15 + DY - 180, "AWS Cloud \u2013 sandbox account", fill="#fcfbff", stroke="#232F3E",
              icon_name="grp-cloud", width=1.4)


def region_box() -> None:
    container(45, 215, 1500, CICD_Y + 170 + 15 - 215, "Region us-west-2", fill="#f9fcfd", stroke="#00A4A6", dash="6 4", icon_name="grp-region",
              label_color="#00777a")


def global_strip() -> None:
    # Drawn in final coordinates (no DY shift): Route 53 is global, ACM for CloudFront lives in us-east-1. Both sit outside the us-west-2 Region box.
    container(60, 215, 380, 140, "Global (not in a Region)", fill="#fbfaff", stroke="#8a96a3", dash="6 4", label_color="#16325c")
    card(80, 248, 340, 96, "route53", "Amazon Route 53", [
        "optional: only with -c siteDomain=...",
        "existing public hosted zone, looked up",
        "apex alias A/AAAA \u2192 CloudFront",
        "domain at Namecheap, NS delegated",
    ], icon_size=38)
    container(1130, 215, 415, 140, "us-east-1 \u2013 stack SoundAlongCertificate", fill="#f9fcfd", stroke="#00A4A6", dash="6 4",
              icon_name="grp-region", label_color="#00777a")
    card(1145, 248, 385, 96, "acm", "AWS Certificate Manager", [
        "optional: one public certificate for siteDomain",
        "DNS-validated through the Route 53 zone",
        "CloudFront reads certificates only from us-east-1",
        "default without it: the *.cloudfront.net address",
    ], icon_size=38)


def edge_layer() -> None:
    container(440, 250, 660, 88, "", fill="#fff5e8", stroke="#f5a623")
    icon("cloudfront", 455, 270, 48)
    text(514, 284, "Amazon CloudFront distribution", size=14, weight="bold")
    text(514, 302, "HTTPS (redirect) \u2022 PriceClass 100", size=11.5, color="#3d4b5c")
    text(514, 318, "security headers \u2022 Origin Access Control to S3", size=11.5, color="#3d4b5c")
    for i, (path, target) in enumerate((("/*", "S3 app/ (web app, cached)"),
                                        ("/data/*", "S3 data/ (audio cache policy)"),
                                        ("/api/*", "CMS API (no cache, all methods)"))):
        cy = 260 + i * 25
        rect(812, cy, 276, 21, fill="#ffffff", stroke="#f3c27a", rx=5)
        text(820, cy + 15, path, size=11.5, weight="bold", color="#b45f00")
        text(880, cy + 15, "\u2192 " + target, size=11.5, color="#3d4b5c")


def cms_layer() -> None:
    container(65, 370, 425, 327, "VPC \u2013 1 AZ, no NAT gateway", fill="#f2fbf1", stroke="#3F8624", icon_name="grp-vpc",
              sub="cmsHost=ec2 (default)", label_color="#2c6b17")
    container(80, 418, 395, 267, "Public subnet /24", fill="#e8f6e3", stroke="#7AA116", icon_name="grp-public", label_color="#4d7a0c")
    card(95, 455, 365, 148, "ec2", "CMS API \u2013 Amazon EC2", [
        "t4g.small \u2022 Amazon Linux 2023 arm64 \u2022 IMDSv2",
        "Node 18 systemd service on :8080",
        "encrypted 8 GB gp3 \u2022 app bundle from CDK asset",
        "also serves the quiz, teacher question review,",
        "read-aloud class insights and school switches",
        "its S3 role reads data/*.timing.json and writes",
        "only data/*.questions.json (plus raw/*)",
    ])
    rect(95, 615, 175, 58, fill="#ffffff", stroke="#cfd8e3", rx=6)
    text(105, 634, "Security group", size=12, weight="bold")
    text(105, 650, "in: CloudFront prefix list", size=11, color="#3d4b5c")
    text(105, 665, ":8080 only, no SSH", size=11, color="#3d4b5c")
    rect(280, 615, 145, 58, fill="#ffffff", stroke="#cfd8e3", rx=6)
    icon("igw", 286, 624, 38)
    text(330, 640, "Internet", size=12, weight="bold")
    text(330, 656, "gateway", size=12, weight="bold")

    rect(65, 712, 360, 90, fill="#fffdf7", stroke="#8a96a3", dash="6 4", rx=10)
    icon("lambda", 77, 726, 40)
    text(127, 738, "Option: cmsHost=lambda", size=13, weight="bold")
    text(127, 755, "ApiFunction \u2022 Node 18 \u2022 arm64 \u2022 512 MB", size=11.5, color="#3d4b5c")
    text(127, 771, "Function URL (AWS_IAM), signed by", size=11.5, color="#3d4b5c")
    text(127, 787, "CloudFront OAC; replaces the VM", size=11.5, color="#3d4b5c")


def processing_layer() -> None:
    container(540, 370, 620, 490, "Audio Generation Pipeline", fill="#eef5fd", stroke="#3B82C4",
              sub="asynchronous \u2022 one Step Functions execution per submitted text")
    card(560, 418, 580, 84, "stepfunctions", "AWS Step Functions \u2013 GenerateStateMachine (Standard)", [
        "IsDocument choice \u2022 8 h timeout \u2022 one execution per submitted text",
        "short text: Generator \u2192 Questions \u2192 Translation, straight through",
        "long document: chunks one at a time \u2192 stitch \u2192 ONE passage",
    ], icon_size=38)
    # Lane A: a short text runs straight through.
    text(560, 522, "SHORT TEXT \u2013 runs straight through", size=12, weight="bold", color="#16325c")
    card(560, 530, 180, 116, "lambda", "Generator", [
        "mode=generate",
        "container image, arm64",
        "parse \u2192 TTS \u2192 MP3",
        "+ word timing JSON",
        "Amazon Polly (default)",
    ], icon_size=34)
    card(760, 530, 180, 116, "lambda", "Questions", [
        "Python 3.14 \u2022 256 MB",
        "drafts 4 questions",
        "English passages only",
        "best effort, off unless",
        "questionsEnabled=true",
    ], icon_size=34)
    card(960, 530, 180, 116, "lambda", "Translation", [
        "same Generator image",
        "mode=translate",
        "Amazon Translate (default)",
        "built-in Opus-MT only",
        "as the sentence fallback",
    ], icon_size=34)
    arrow([(740, 588), (760, 588)])
    arrow([(940, 588), (960, 588)])
    # Lane B: a long document is narrated in internal chunks, then joined.
    text(560, 664, "LONG DOCUMENT \u2013 chunks one at a time, then ONE joined passage", size=12, weight="bold", color="#16325c")
    card(560, 672, 180, 116, "stepfunctions", "EachChunk loop", [
        "Map, one chunk at a",
        "time: generate, then",
        "translate (Generator)",
        "ChunkDone counts it",
        "on the job (table)",
    ], icon_size=34)
    card(760, 672, 180, 116, "lambda", "Stitch", [
        "Generator mode=stitch",
        "joins the chunks into",
        "ONE passage per",
        "language, then deletes",
        "raw/work/<id>/",
    ], icon_size=34)
    card(960, 672, 180, 116, "lambda", "Questions (once)", [
        "same Lambda as above",
        "once per document,",
        "English only (choice),",
        "best effort, after the",
        "join",
    ], icon_size=34)
    arrow([(740, 730), (760, 730)])
    arrow([(940, 730), (960, 730)])
    for i, line in enumerate((
        "Generator Lambda = one image, three modes: generate, translate, stitch (6 GB, 15 min).",
        "Questions and translation are caught: they never fail an audio job.",
        "A crash marks the job failed in DynamoDB. Bedrock callers stay under ~1 request/s.",
    )):
        text(560, 812 + i * 17, line, size=11.5, color="#3d4b5c", italic=(i == 2))


def ai_layer() -> None:
    container(1185, 370, 345, 490, "AI Services", fill="#f4fbf8", stroke="#01A88D",
              sub="optional \u2022 enabled per deploy flag (-c ...)", label_color="#016b5a")
    card(1200, 418, 315, 95, "polly", "Amazon Polly", [
        "ttsEngine=polly (default; kokoro optional)",
        "Neural voices Joanna (en), Lupe (es)",
        "polly:SynthesizeSpeech only",
    ])
    card(1200, 530, 315, 95, "bedrock", "Amazon Bedrock", [
        "questionsModel / translateModel",
        "bedrock:InvokeModel on one model",
        "(or its us. inference profile)",
    ])
    card(1200, 642, 315, 95, "translate", "Amazon Translate", [
        "translateModel=amazon:informal (default)",
        "no PyTorch involved; formal / informal",
        "translate:TranslateText only",
    ])
    arrow([(1142, 588), (1198, 588)])
    rect(1200, 752, 315, 92, fill="#fffdf7", stroke="#8a96a3", dash="6 4", rx=8)
    text(1212, 772, "No AWS speech service", size=12, weight="bold")
    for i, line in enumerate((
        "Read-aloud speech recognition runs in",
        "the learner's browser. No Transcribe or",
        "other speech service is called, and no",
        "learner audio reaches this account.",
    )):
        text(1212, 790 + i * 14, line, size=11, color="#3d4b5c")


def data_layer() -> None:
    y = DATA_Y
    container(65, y, 840, DATA_H, "Data", fill="#f7f3fd", stroke="#8C4FFF", sub=None, label_color="#5a2fb0")
    text(120, y + 21, "private \u2022 encrypted \u2022 SSL only", size=11, color="#5a2fb0")
    card(80, y + 30, 445, 148, "s3", "Amazon S3 \u2013 site and content bucket", [
        "app/  web build (cached by CloudFront)",
        "data/  MP3, timing and cards (CloudFront)",
        "data/<id>.questions.json  approved questions only",
        "raw/  uploads and source text (expire after 7 days)",
        "raw/work/<id>/  temp chunk folder, deleted after the join",
        "raw/questions/  unpublished drafts (expire with raw/)",
        "Block Public Access \u2022 SSE-S3 \u2022 SSL only",
    ], line_size=11)
    card(545, y + 30, 345, 148, "dynamodb", "Amazon DynamoDB \u2013 Table", [
        "pk / sk \u2022 on-demand \u2022 TTL attribute",
        "jobs (with chunk progress) and passages",
        "CMS state: settings, pronunciations",
        "read-aloud counters: anonymous word",
        "counts per passage and class, 400-day expiry",
        "class settings (mic, share, readers)",
    ], line_size=11)


def ops_layer() -> None:
    y = DATA_Y
    container(925, y, 605, DATA_H, "Operations & Governance", fill="#fdf4f7", stroke="#E7157B", label_color="#a50f58")
    for i, (name, title, lines) in enumerate((
        ("cloudwatch", "CloudWatch", ("Lambda log groups:", "API, Generator,", "Questions", "1-week retention")),
        ("iam", "IAM", ("one role per component", "least privilege:", "S3 by prefix, one", "Bedrock model")),
        ("budgets", "AWS Budgets", ("$500 / month", "email 25/50/80%", "only when alertEmail", "is set")),
        ("ssm", "Systems Mgr", ("Session Manager", "VM shell, no SSH", "(cmsHost=ec2 only)")),
    )):
        x = 940 + i * 146
        rect(x, y + 30, 138, 148, fill="#ffffff", stroke="#cfd8e3", rx=8)
        icon(name, x + 8, y + 38, 30)
        text(x + 44, y + 57, title, size=12, weight="bold")
        for j, line in enumerate(lines):
            text(x + 10, y + 92 + j * 17, line, size=11, color="#3d4b5c")


def cicd_layer() -> None:
    container(65, CICD_Y, 1465, 170, "CI/CD \u2013 SoundAlongPipeline stack", fill="#fffaeb", stroke="#E0A100",
              sub="every push to main rebuilds and deploys SoundAlongStack on AWS (not on a laptop)", label_color="#8a5a00")
    cards = (
        ("devtools", "GitHub connection", ["AWS CodeStar Connections v2", "authorized once in the console"]),
        ("codepipeline", "AWS CodePipeline (V2)", ["sound-along-pipeline", "Source \u2192 BuildAndDeploy", "artifacts in an S3 bucket"]),
        ("codebuild", "AWS CodeBuild", ["ARM LARGE, privileged (Docker)", "build web \u2022 bundle API", "npx aws-cdk deploy"]),
        ("ecr", "Amazon ECR", ["arm64 generator image", "(~4.6 GB, CDK asset)", "+ S3 file assets"]),
        ("cloudformation", "AWS CloudFormation", ["SoundAlongStack", "via CDK bootstrap roles", "(cdk-hnb659fds-*)"]),
    )
    for i, (name, title, lines) in enumerate(cards):
        card(85 + i * 295, CICD_Y + 50, 255, 105, name, title, lines)
        if i:
            arrow([(85 + i * 295 - 40, CICD_Y + 102), (85 + i * 295 - 2, CICD_Y + 102)], color=DEPLOY, dash="6 4")


def external() -> None:
    gy = CICD_Y + 170 + 15 + 25  # just below the AWS Cloud box
    card(85, gy, 340, 62, "git", "GitHub \u2013 team49-sound-along/sound-along", ["developers push to the main branch"], icon_size=38)
    arrow([(212, gy), (212, CICD_Y + 157)], color=DEPLOY, dash="6 4", label="push triggers pipeline", label_at=(222, gy - 10), label_anchor="start")
    text(1530, gy + 50, "Built from infra/sound_along/*.py. Icons: AWS Architecture Icons (07-31-2026 package; ACM icon redrawn).",
         size=11, color="#6b7a8c", anchor="end", italic=True)
    text(1530, gy + 68, "Regenerate with: python docs/architecture/build_diagram.py", size=11, color="#6b7a8c", anchor="end", italic=True)


def top_flows() -> None:
    # Final coordinates (no DY shift): arrows from the browsers and from the global strip down to CloudFront (drawn at y = 250 + DY).
    top = 250 + DY - 2
    arrow([(450, 160), (450, 170), (370, 170), (370, 246)], color=USER, dash="4 3", label="DNS lookup", label_at=(380, 205), label_anchor="start")
    arrow([(330, 346), (330, 275 + DY), (438, 275 + DY)], color=SERVICE, label="alias", label_at=(338, 275 + DY - 8), label_anchor="start")
    arrow([(1145, 296), (1080, 296), (1080, top)], color=SERVICE, label="viewer certificate", label_at=(1074, 290), label_anchor="end")
    arrow([(575, 160), (575, top)], color=USER, label="HTTPS", label_at=(585, 205), label_anchor="start")
    arrow([(925, 160), (925, top)], color=USER, label="HTTPS", label_at=(935, 205), label_anchor="start")


def flows() -> None:
    d = DATA_Y + 28  # top of the S3 / DynamoDB cards, minus the arrowhead
    pb = 860         # bottom of the pipeline container
    arrow([(440, 300), (400, 300), (400, 453)], color=USER, label="/api/*  HTTP :8080", label_at=(396, 352), label_anchor="end")
    arrow([(515, 338), (515, d)], color=USER, label="/* and /data/* via OAC", label_at=(533, 845), label_rotate=-90, label_anchor="start")
    arrow([(460, 462), (558, 462)], label="StartExecution", label_at=(500, 492), label_anchor="middle")
    arrow([(445, 603), (445, d)], label="S3 + DynamoDB R/W", label_at=(439, 890), label_rotate=-90, label_anchor="start")
    arrow([(600, pb), (600, pb + 25), (480, pb + 25), (480, d)], label="raw/ in, data/ out", label_at=(610, pb + 19), label_anchor="start")
    arrow([(760, pb), (760, d)], label="job status", label_at=(770, pb + 19), label_anchor="start")


def legend() -> None:
    x, w = 1582, 222
    rect(x, 92, w, 600, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 118, "Legend", size=15, weight="bold", color="#16325c")
    entries = (
        ("route53", "Amazon Route 53"), ("acm", "AWS Certificate Manager"), ("cloudfront", "Amazon CloudFront"), ("ec2", "Amazon EC2"), ("lambda", "AWS Lambda"),
        ("stepfunctions", "AWS Step Functions"), ("s3", "Amazon S3"), ("dynamodb", "Amazon DynamoDB"),
        ("polly", "Amazon Polly"), ("bedrock", "Amazon Bedrock"), ("translate", "Amazon Translate"),
        ("vpc", "Amazon VPC"), ("cloudwatch", "Amazon CloudWatch"), ("iam", "AWS IAM"),
        ("budgets", "AWS Budgets"), ("ssm", "AWS Systems Manager"), ("codepipeline", "AWS CodePipeline"),
        ("codebuild", "AWS CodeBuild"), ("ecr", "Amazon ECR"), ("cloudformation", "AWS CloudFormation"),
    )
    for i, (name, label) in enumerate(entries):
        y = 132 + i * 27.5
        icon(name, x + 14, y, 24)
        text(x + 48, y + 17, label, size=12)

    rect(x, 702, w, 166, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 728, "Boundaries", size=15, weight="bold", color="#16325c")
    for i, (label, stroke, fill, dash) in enumerate((
        ("AWS account", "#232F3E", "#fcfbff", None),
        ("Region", "#00A4A6", "#f9fcfd", "6 4"),
        ("VPC", "#3F8624", "#f2fbf1", None),
        ("Public subnet", "#7AA116", "#e8f6e3", None),
        ("Optional / alternative", "#8a96a3", "#fffdf7", "6 4"),
    )):
        y = 740 + i * 26
        rect(x + 14, y, 40, 18, fill=fill, stroke=stroke, dash=dash, width=1.6, rx=4)
        text(x + 64, y + 14, label, size=12)

    rect(x, 881, w, 140, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 907, "Key flows", size=15, weight="bold", color="#16325c")
    for i, (label, color, dash) in enumerate((
        ("User / web traffic", USER, None),
        ("Service and data flow", SERVICE, None),
        ("Deployment flow", DEPLOY, "6 4"),
    )):
        y = 930 + i * 28
        arrow([(x + 14, y), (x + 60, y)], color=color, dash=dash)
        text(x + 70, y + 4, label, size=12)

    rect(x, 1034, w, 232, fill="#f3f8fd", stroke="#d5dbe3", rx=10)
    text(x + 14, 1058, "Deploy defaults", size=14, weight="bold", color="#16325c")
    for i, line in enumerate((
        "cmsHost=ec2, ttsEngine=polly",
        "readerInsights=false: per-reader",
        "codes are off when deployed",
        "(needs teacher sign-in first)",
        "siteDomain: optional custom",
        "domain; the default is the",
        "*.cloudfront.net address",
        "Polly, Bedrock, Translate and",
        "Budgets exist only when their",
        "-c flag is passed to cdk deploy.",
        "Every resource: project=sound-along",
    )):
        text(x + 14, 1080 + i * 15.5, line, size=11.5, color="#3d4b5c")


def build_svg() -> str:
    out.clear()
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="{FONT}">'
    )
    defs()
    out.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>')
    header()
    actors()
    aws_cloud()
    global_strip()
    out.append(f'<g transform="translate(0,{DY})">')  # the Region and everything below it
    region_box()
    edge_layer()
    cms_layer()
    processing_layer()
    ai_layer()
    data_layer()
    ops_layer()
    cicd_layer()
    external()
    flows()
    out.append("</g>")
    top_flows()
    legend()
    out.append("</svg>")
    return "\n".join(out)


def find_browser() -> str | None:
    for candidate in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return shutil.which("msedge") or shutil.which("google-chrome") or shutil.which("chromium")


def render_png() -> None:
    browser = find_browser()
    if not browser:
        print("No Edge/Chrome found; skipped PNG.")
        return
    # On macOS, headless Chrome/Edge lays the page out in a viewport shorter than the window and leaves the bottom
    # of the image white. Render a taller window there, then crop back to the diagram height with sips.
    pad = 120 if sys.platform == "darwin" and shutil.which("sips") else 0
    target = SVG_OUT
    wrapper = None
    if pad:
        # sips crops from the CENTRE, so the picture is placed pad/2 CSS pixels down: the centre crop then removes the empty strips only.
        wrapper = SVG_OUT.with_name("_render.html")
        wrapper.write_text(
            f'<!doctype html><meta charset="utf-8"><body style="margin:0;padding-top:{pad // 2}px;background:#fff">'
            f'<img src="{SVG_OUT.name}" width="{WIDTH}" height="{HEIGHT}" style="display:block"></body>',
            encoding="utf-8",
        )
        target = wrapper
    try:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
             f"--window-size={WIDTH},{HEIGHT + pad}", f"--screenshot={PNG_OUT}", target.as_uri()],
            check=True, timeout=120, capture_output=True,
        )
        if pad:
            subprocess.run(["sips", "--cropToHeightWidth", str(HEIGHT * 2), str(WIDTH * 2), str(PNG_OUT)],
                           check=True, timeout=60, capture_output=True)
    finally:
        if wrapper is not None:
            wrapper.unlink(missing_ok=True)
    print(f"wrote {PNG_OUT}")


if __name__ == "__main__":
    SVG_OUT.write_text(build_svg(), encoding="utf-8")
    print(f"wrote {SVG_OUT}")
    render_png()
