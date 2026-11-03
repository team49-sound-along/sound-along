"""Rules for place pictures, shared by the demo build script (scripts/place_images.py) and the live publish step (enrich_places.py).

Only free licences, only real JPEG/PNG bytes (never SVG), plain-text alt text and credits, and file names that carry a content hash.
Standard library only; lives in synth because the generator Lambda image ships only parse and synth.
"""
from __future__ import annotations

import hashlib
import html
import re

NAME_PATTERN = re.compile(r"[0-9a-f-]{36}\.place-[a-z0-9-]{1,60}-[0-9a-f]{8}\.(?:jpg|png)")
MAX_ALT = 125  # a screen reader reads alt text in one go; longer belongs in the caption
MAX_BYTES = 400_000
THUMB_WIDTH = 500
PACE_SECONDS = 1.2
USER_AGENT = "SoundAlongCards/1.0 (https://github.com/rohanreigns007/sound-along; one-off content build, no personal data)"
_BLOCKED = re.compile(r"\b(NC|ND)\b|NON.?COMMERCIAL|NO.?DERIV|GFDL|FAIR USE|ALL RIGHTS")
_ALLOWED = re.compile(r"^(CC0( .*)?|CC[ -]BY(-SA)?( \d(\.\d)?)?( .*)?|PUBLIC DOMAIN|PD([ -].*)?)$")


# ---- pure helpers (tested) -------------------------------------------------------------------------------------------------------
def license_ok(name: str | None) -> bool:
    """Only free licences: CC0, public domain, CC BY, CC BY-SA. Non-commercial, no-derivatives, GFDL and unknown are refused."""
    if not name or not name.strip():
        return False
    upper = name.strip().upper()
    return not _BLOCKED.search(upper) and bool(_ALLOWED.match(upper))


def clean_artist(value: str | None) -> str:
    """Plain-text author from Commons' HTML credit: tags removed, entities decoded, whitespace collapsed, capped at 80 characters."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value or ""))).strip()
    text = text.replace("<", "").replace(">", "")
    return text[:80].strip() or "Unknown author"


def credit_line(artist: str, license_name: str) -> str:
    kind = "Image" if license_name.strip().upper().startswith(("PUBLIC DOMAIN", "PD", "CC0")) else "Photo"
    return f"{kind}: {artist}, {license_name}, via Wikimedia Commons"


def image_ext(data: bytes) -> str | None:
    """"jpg" or "png" when the BYTES are really that, otherwise None. SVG, HTML and everything else is refused."""
    if len(data) >= 4 and data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from the file header of a JPEG or PNG, or None. Lets the reader reserve the picture's space and fit it without cropping."""
    if image_ext(data) == "png":
        if len(data) >= 24 and data[12:16] == b"IHDR":
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        return None
    if image_ext(data) != "jpg":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xD9, 0xDA):
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "place"


def target_name(passage_id: str, place: str, data: bytes) -> str:
    """<passage id>.place-<slug>-<8 hex of the content hash>.<ext>: the hash makes the file safe to cache for a year."""
    ext = image_ext(data)
    if ext is None:
        raise ValueError("not a JPEG or PNG image")
    return f"{passage_id}.place-{slug(place)}-{hashlib.sha256(data).hexdigest()[:8]}.{ext}"


def alt_problem(alt: object, place: str) -> str | None:
    if not isinstance(alt, str) or not alt.strip():
        return "alt text is required for every picture"
    if len(alt) > MAX_ALT:
        return f"alt text is over {MAX_ALT} characters"
    if "<" in alt or ">" in alt:
        return "alt text must be plain text"
    if alt.strip().lower() == place.strip().lower():
        return "alt text must describe the picture, not repeat the place name"
    return None


