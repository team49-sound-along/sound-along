"""Builds the Sound Along architecture diagram (SVG, plus PNG through headless Edge or Chrome).

The layout mirrors infra/sound_along/*.py. Icons in ./icons come from the official AWS Architecture Icons package
(https://aws.amazon.com/architecture/icons/, 07-31-2026 release) and are embedded so the SVG is self-contained.

    python build_diagram.py            # writes sound-along-architecture.svg and .png next to this file
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
SVG_OUT = HERE / "sound-along-architecture.svg"
PNG_OUT = HERE / "sound-along-architecture.png"
WIDTH, HEIGHT = 1820, 1250
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
    text(1800, 56, "Stacks: SoundAlongStack + SoundAlongPipeline", size=12, color="#4a6a8f", anchor="end")


def actors() -> None:
    card(430, 92, 290, 68, "users", "Learners & Teachers", ["Browser: read-along player", "audio with word-by-word timing"])
    card(780, 92, 290, 68, "client", "Content Authors", ["Browser: CMS pages", "upload, generate, review cards"])


def aws_cloud() -> None:
    container(30, 180, 1530, 945, "AWS Cloud \u2013 sandbox account", fill="#fcfbff", stroke="#232F3E", icon_name="grp-cloud", width=1.4)
    container(45, 215, 1500, 895, "Region us-west-2", fill="#f9fcfd", stroke="#00A4A6", dash="6 4", icon_name="grp-region",
              label_color="#00777a")


def dns_layer() -> None:
    # Route 53 sits in front of CloudFront: it resolves the custom domain to the distribution.
    card(115, 250, 300, 88, "route53", "Amazon Route 53", [
        "public hosted zone: sound-along.online",
        "apex alias A/AAAA \u2192 CloudFront",
        "domain at Namecheap, NS delegated",
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
    container(65, 370, 425, 265, "VPC \u2013 1 AZ, no NAT gateway", fill="#f2fbf1", stroke="#3F8624", icon_name="grp-vpc",
              sub="cmsHost=ec2 (default)", label_color="#2c6b17")
    container(80, 418, 395, 205, "Public subnet /24", fill="#e8f6e3", stroke="#7AA116", icon_name="grp-public", label_color="#4d7a0c")
    card(95, 455, 365, 86, "ec2", "CMS API \u2013 Amazon EC2", [
        "t4g.small \u2022 Amazon Linux 2023 arm64 \u2022 IMDSv2",
        "Node 18 systemd service on :8080",
        "encrypted 8 GB gp3 \u2022 app bundle from CDK asset",
    ])
    rect(95, 553, 175, 58, fill="#ffffff", stroke="#cfd8e3", rx=6)
    text(105, 572, "Security group", size=12, weight="bold")
    text(105, 588, "in: CloudFront prefix list", size=11, color="#3d4b5c")
    text(105, 603, ":8080 only, no SSH", size=11, color="#3d4b5c")
    rect(280, 553, 145, 58, fill="#ffffff", stroke="#cfd8e3", rx=6)
    icon("igw", 286, 562, 38)
    text(330, 578, "Internet", size=12, weight="bold")
    text(330, 594, "gateway", size=12, weight="bold")

    rect(65, 650, 360, 90, fill="#fffdf7", stroke="#8a96a3", dash="6 4", rx=10)
    icon("lambda", 77, 664, 40)
    text(127, 676, "Option: cmsHost=lambda", size=13, weight="bold")
    text(127, 693, "ApiFunction \u2022 Node 18 \u2022 arm64 \u2022 512 MB", size=11.5, color="#3d4b5c")
    text(127, 709, "Function URL (AWS_IAM), signed by", size=11.5, color="#3d4b5c")
    text(127, 725, "CloudFront OAC; replaces the VM", size=11.5, color="#3d4b5c")


def processing_layer() -> None:
    container(540, 370, 620, 370, "Audio Generation Pipeline", fill="#eef5fd", stroke="#3B82C4",
              sub="asynchronous \u2022 one Step Functions execution per submitted document")
    card(560, 418, 580, 58, "stepfunctions", "AWS Step Functions \u2013 GenerateStateMachine (Standard)", [
        "Map over parts, max concurrency 1 \u2022 8 h timeout \u2022 a crashed part is marked failed in DynamoDB",
    ], icon_size=38)
    card(560, 505, 180, 118, "lambda", "Generator", [
        "container image, arm64",
        "4 GB \u2022 15 min max",
        "parse \u2192 TTS \u2192 MP3",
        "+ word timing JSON",
        "Kokoro TTS built in",
    ], icon_size=34)
    card(760, 505, 180, 118, "lambda", "Questions", [
        "Python 3.14 \u2022 256 MB",
        "drafts 4 questions",
        "English passages only",
        "best effort, off unless",
        "questionsEnabled=true",
    ], icon_size=34)
    card(960, 505, 180, 118, "lambda", "Translation", [
        "same generator image",
        "mode=translate",
        "Opus-MT built in, or",
        "Bedrock / Amazon",
        "Translate if configured",
    ], icon_size=34)
    arrow([(650, 476), (650, 505)])
    arrow([(740, 564), (760, 564)])
    arrow([(940, 564), (960, 564)])
    for i, line in enumerate((
        "Per part: Generator \u2192 (status = done) \u2192 Questions (English) \u2192 Translation.",
        "Questions and translation are caught: they never fail an audio job.",
        "Bedrock callers pace themselves to stay under ~1 request/s for the account.",
    )):
        text(560, 650 + i * 18, line, size=11.5, color="#3d4b5c", italic=(i == 2))


def ai_layer() -> None:
    container(1185, 370, 345, 370, "AI Services", fill="#f4fbf8", stroke="#01A88D",
              sub="optional \u2022 enabled per deploy flag (-c ...)", label_color="#016b5a")
    card(1200, 418, 315, 95, "polly", "Amazon Polly", [
        "ttsEngine=polly (default: Kokoro)",
        "Neural voices Joanna (en), Lupe (es)",
        "polly:SynthesizeSpeech only",
    ])
    card(1200, 525, 315, 95, "bedrock", "Amazon Bedrock", [
        "questionsModel / translateModel",
        "bedrock:InvokeModel on one model",
        "(or its us. inference profile)",
    ])
    card(1200, 632, 315, 95, "translate", "Amazon Translate", [
        "translateModel=amazon",
        "(formal / informal variants)",
        "translate:TranslateText only",
    ])
    arrow([(1160, 564), (1198, 564)])


def data_layer() -> None:
    container(65, 785, 840, 122, "Data", fill="#f7f3fd", stroke="#8C4FFF", sub=None, label_color="#5a2fb0")
    text(120, 806, "private \u2022 encrypted \u2022 SSL only", size=11, color="#5a2fb0")
    card(80, 815, 445, 82, "s3", "Amazon S3 \u2013 site and content bucket", [
        "app/ web build \u2022 data/ MP3, timing, cards (served by CloudFront)",
        "raw/ uploads + drafts (expire after 7 days) \u2022 Block Public Access",
    ], line_size=11)
    card(545, 815, 345, 82, "dynamodb", "Amazon DynamoDB \u2013 Table", [
        "pk / sk \u2022 on-demand \u2022 TTL attribute",
        "jobs, passages and CMS state",
    ])


def ops_layer() -> None:
    container(925, 785, 605, 122, "Operations & Governance", fill="#fdf4f7", stroke="#E7157B", label_color="#a50f58")
    for i, (name, title, l1, l2) in enumerate((
        ("cloudwatch", "CloudWatch", "Lambda log groups", "1-week retention"),
        ("iam", "IAM", "one role per part", "least privilege"),
        ("budgets", "AWS Budgets", "$500 / month", "email 25/50/80%"),
        ("ssm", "Systems Mgr", "Session Manager", "VM shell, no SSH"),
    )):
        x = 940 + i * 146
        rect(x, 815, 138, 82, fill="#ffffff", stroke="#cfd8e3", rx=8)
        icon(name, x + 8, 823, 30)
        text(x + 44, 842, title, size=12, weight="bold")
        text(x + 10, 870, l1, size=11, color="#3d4b5c")
        text(x + 10, 886, l2, size=11, color="#3d4b5c")


def cicd_layer() -> None:
    container(65, 925, 1465, 170, "CI/CD \u2013 SoundAlongPipeline stack", fill="#fffaeb", stroke="#E0A100",
              sub="every push to main rebuilds and deploys SoundAlongStack on AWS (not on a laptop)", label_color="#8a5a00")
    cards = (
        ("devtools", "GitHub connection", ["AWS CodeStar Connections v2", "authorized once in the console"]),
        ("codepipeline", "AWS CodePipeline (V2)", ["sound-along-pipeline", "Source \u2192 BuildAndDeploy", "artifacts in an S3 bucket"]),
        ("codebuild", "AWS CodeBuild", ["ARM LARGE, privileged (Docker)", "build web \u2022 bundle API", "npx aws-cdk deploy"]),
        ("ecr", "Amazon ECR", ["arm64 generator image", "(~4.6 GB, CDK asset)", "+ S3 file assets"]),
        ("cloudformation", "AWS CloudFormation", ["SoundAlongStack", "via CDK bootstrap roles", "(cdk-hnb659fds-*)"]),
    )
    for i, (name, title, lines) in enumerate(cards):
        card(85 + i * 295, 975, 255, 105, name, title, lines)
        if i:
            arrow([(85 + i * 295 - 40, 1027), (85 + i * 295 - 2, 1027)], color=DEPLOY, dash="6 4")


def external() -> None:
    card(85, 1150, 340, 62, "git", "GitHub \u2013 team49-sound-along/sound-along", ["developers push to the main branch"], icon_size=38)
    arrow([(212, 1150), (212, 1082)], color=DEPLOY, dash="6 4", label="push triggers pipeline", label_at=(222, 1140), label_anchor="start")
    text(1530, 1200, "Built from infra/sound_along/*.py. Icons: AWS Architecture Icons (07-31-2026 package).",
         size=11, color="#6b7a8c", anchor="end", italic=True)
    text(1530, 1218, "Regenerate with: python docs/architecture/build_diagram.py", size=11, color="#6b7a8c", anchor="end", italic=True)


def flows() -> None:
    # DNS resolution: user looks up the name in Route 53, which aliases to CloudFront.
    arrow([(455, 126), (265, 126), (265, 248)], color=USER, dash="4 3", label="DNS lookup", label_at=(275, 160), label_anchor="start")
    arrow([(415, 294), (438, 294)], color=SERVICE, label="alias", label_at=(426, 284), label_anchor="middle")
    arrow([(575, 160), (575, 248)], color=USER, label="HTTPS", label_at=(585, 210), label_anchor="start")
    arrow([(925, 160), (925, 248)], color=USER, label="HTTPS", label_at=(935, 210), label_anchor="start")
    arrow([(440, 300), (400, 300), (400, 453)], color=USER, label="/api/*  HTTP :8080", label_at=(396, 352), label_anchor="end")
    arrow([(515, 338), (515, 813)], color=USER, label="/* and /data/* via OAC", label_at=(533, 735), label_rotate=-90, label_anchor="start")
    arrow([(460, 462), (558, 462)], label="StartExecution", label_at=(500, 492), label_anchor="middle")
    arrow([(445, 541), (445, 813)], label="S3 + DynamoDB R/W", label_at=(439, 765), label_rotate=-90, label_anchor="start")
    arrow([(600, 740), (600, 768), (480, 768), (480, 813)], label="raw/ in, data/ out", label_at=(610, 762), label_anchor="start")
    arrow([(760, 740), (760, 813)], label="job status", label_at=(770, 762), label_anchor="start")


def legend() -> None:
    x, w = 1582, 222
    rect(x, 92, w, 572, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 118, "Legend", size=15, weight="bold", color="#16325c")
    entries = (
        ("route53", "Amazon Route 53"), ("cloudfront", "Amazon CloudFront"), ("ec2", "Amazon EC2"), ("lambda", "AWS Lambda"),
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

    rect(x, 674, w, 166, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 700, "Boundaries", size=15, weight="bold", color="#16325c")
    for i, (label, stroke, fill, dash) in enumerate((
        ("AWS account", "#232F3E", "#fcfbff", None),
        ("Region", "#00A4A6", "#f9fcfd", "6 4"),
        ("VPC", "#3F8624", "#f2fbf1", None),
        ("Public subnet", "#7AA116", "#e8f6e3", None),
        ("Optional / alternative", "#8a96a3", "#fffdf7", "6 4"),
    )):
        y = 712 + i * 26
        rect(x + 14, y, 40, 18, fill=fill, stroke=stroke, dash=dash, width=1.6, rx=4)
        text(x + 64, y + 14, label, size=12)

    rect(x, 853, w, 140, fill="#ffffff", stroke="#d5dbe3", rx=10)
    text(x + 14, 879, "Key flows", size=15, weight="bold", color="#16325c")
    for i, (label, color, dash) in enumerate((
        ("User / web traffic", USER, None),
        ("Service and data flow", SERVICE, None),
        ("Deployment flow", DEPLOY, "6 4"),
    )):
        y = 902 + i * 28
        arrow([(x + 14, y), (x + 60, y)], color=color, dash=dash)
        text(x + 70, y + 4, label, size=12)

    rect(x, 1006, w, 119, fill="#f3f8fd", stroke="#d5dbe3", rx=10)
    text(x + 14, 1030, "Deploy defaults", size=14, weight="bold", color="#16325c")
    for i, line in enumerate((
        "cmsHost=ec2, ttsEngine=kokoro",
        "Polly, Bedrock, Translate and",
        "Budgets exist only when their",
        "-c flag is passed to cdk deploy.",
        "Every resource: project=sound-along",
    )):
        text(x + 14, 1050 + i * 15.5, line, size=11.5, color="#3d4b5c")


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
    dns_layer()
    edge_layer()
    cms_layer()
    processing_layer()
    ai_layer()
    data_layer()
    ops_layer()
    cicd_layer()
    external()
    flows()
    legend()
    out.append("</svg>")
    return "\n".join(out)


def find_browser() -> str | None:
    for candidate in (
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
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
         f"--window-size={WIDTH},{HEIGHT}", f"--screenshot={PNG_OUT}", SVG_OUT.as_uri()],
        check=True, timeout=120, capture_output=True,
    )
    print(f"wrote {PNG_OUT}")


if __name__ == "__main__":
    SVG_OUT.write_text(build_svg(), encoding="utf-8")
    print(f"wrote {SVG_OUT}")
    render_png()
