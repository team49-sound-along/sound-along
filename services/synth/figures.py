"""Pictures that ReadWorks passages carry between paragraphs (<figure> with an image, a caption and a credit).

The narration skips figures, so they never reach the audio. This module lists them (extract_figures) and, at build time only, fetches
the image bytes (fetch_figures) so the reader can show them between paragraphs. The images are ReadWorks' own, so they are never committed
to the repository: they live in data/ and the S3 bucket, like the generated audio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urlparse

from place_media import image_ext, image_size, target_name

ALLOWED_HOSTS = frozenset({"dq5qica5h7eg3.cloudfront.net"})  # where ReadWorks serves passage pictures
MAX_BYTES = 3_000_000
MAX_FIGURES = 8


@dataclass(frozen=True)
class Figure:
    after_paragraph: int  # number of paragraphs before the figure: 0 = above the first paragraph
    src: str
    alt: str
    caption: str
    credit: str


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.figures: list[Figure] = []
        self.paragraphs = 0
        self._depth = 0
        self._cur: Optional[dict] = None
        self._field: Optional[str] = None
        self._field_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "figure":
            self._depth += 1
            if self._depth == 1:
                self._cur = {"after": self.paragraphs, "src": "", "alt": "", "caption": [], "credit": []}
        elif self._depth and tag == "img" and self._cur is not None and not self._cur["src"]:
            self._cur["src"], self._cur["alt"] = a.get("src") or "", a.get("alt") or ""
        elif self._depth and tag == "div":
            cls = a.get("class") or ""
            if self._field is None and ("image-caption" in cls or "image-credit" in cls):
                self._field, self._field_depth = ("caption" if "image-caption" in cls else "credit"), 1
            elif self._field is not None:
                self._field_depth += 1
        elif tag == "p" and not self._depth:
            self.paragraphs += 1

    def handle_endtag(self, tag):
        if tag == "div" and self._field is not None:
            self._field_depth -= 1
            if self._field_depth == 0:
                self._field = None
        elif tag == "figure" and self._depth:
            self._depth -= 1
            if self._depth == 0 and self._cur is not None:
                c = self._cur
                clean = lambda parts: re.sub(r"\s+", " ", " ".join(parts)).strip()  # noqa: E731
                if c["src"]:
                    self.figures.append(Figure(c["after"], c["src"], c["alt"].strip(), clean(c["caption"]), clean(c["credit"])))
                self._cur = None

    def handle_data(self, data):
        if self._depth and self._field and self._cur is not None:
            self._cur[self._field].append(data)


def extract_figures(content_html: str) -> list[Figure]:
    """The figures of a passage, in order, with the paragraph each one follows. Only https pictures from ReadWorks' own host are kept."""
    parser = _Collector()
    parser.feed(content_html or "")
    parser.close()
    ok = []
    for f in parser.figures:
        u = urlparse(f.src)
        if u.scheme == "https" and u.hostname in ALLOWED_HOSTS:
            ok.append(f)
    return ok[:MAX_FIGURES]


def fetch_figures(passage_id: str, figures: list[Figure], http_get: Callable[[str], bytes]) -> tuple[list[dict], dict[str, bytes]]:
    """(figure entries for the cards document, {file name: bytes}). A picture that cannot be fetched or is not a JPEG/PNG is left out, never fatal."""
    entries: list[dict] = []
    images: dict[str, bytes] = {}
    for i, f in enumerate(figures):
        try:
            data = http_get(f.src)
        except Exception:  # noqa: BLE001 (a missing picture must not stop the build)
            continue
        if not data or len(data) > MAX_BYTES or image_ext(data) is None:
            continue
        name = target_name(passage_id, str(i), data, kind="figure")
        size = image_size(data)
        entries.append({"afterParagraph": f.after_paragraph, "imageUrl": f"/data/{name}", "imageAlt": f.alt or "Picture from the passage",
                        **({"caption": f.caption} if f.caption else {}), **({"credit": f.credit} if f.credit else {}),
                        **({"imageWidth": size[0], "imageHeight": size[1]} if size else {})})
        images[name] = data
    return entries, images
