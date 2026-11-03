"""Live place cards for ANY passage, made when it is published (never while a student reads).

For a passage a teacher uploads, find the named places in it, look them up on Wikipedia in ONE batched request, keep only real
places (the article has coordinates, is not a disambiguation page, and has a Wikidata description), and attach a small free-licensed
picture when one exists. Everything is written next to the audio as `<id>.cards.json` plus `<id>.place-<slug>-<hash>.jpg|png`, so the
reader only ever fetches static files from our own origin (no third-party request from a student's browser, no cost per view).

Privacy: the only thing sent off the generator is the NAME of each place the spaCy detector finds (for example "Tower Bridge"), in one query to
Wikipedia. Never the passage text, never other names, nothing about a reader. If the detector is unavailable nothing is sent. A teacher can switch
it off per passage (settings.placeCards = false) and an operator for the deployment (PLACE_CARDS=off).

Safe to run on the live path: it never raises. Offline, blocked, slow or garbage replies give None, and audio and timing still publish.
The result is marked `"reviewed": false`: nobody has looked at these pictures yet (see docs/PLACE_IMAGES.md).

Standard library only (spaCy is used for an extra place detector when it is installed).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from pipeline import tokenize_html
from place_media import image_size, MAX_ALT, MAX_BYTES, NAME_PATTERN, THUMB_WIDTH, alt_problem, clean_artist, credit_line, image_ext, license_ok, slug, target_name

LOG = logging.getLogger(__name__)

MAX_CANDIDATES = 25  # one MediaWiki query takes up to 50 titles; a short passage never needs more
MAX_IMAGES = 10
BUDGET_SECONDS = 25.0
REQUEST_TIMEOUT = 8
USER_AGENT = "SoundAlongCards/1.0 (https://github.com/rohanreigns007/sound-along; live content step, no personal data)"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
_CONNECTORS = {"of", "the", "de", "la", "del", "du", "von", "van", "al", "el"}
_ABBREVIATION = re.compile(r"^[A-Z][a-z]{0,3}\.$")  # Mr. Mrs. Dr. St.
_EDGE = re.compile(r"^[^\w]+|[^\w]+$")
_POSSESSIVE = re.compile(r"['’]s$")
HttpGet = Callable[..., Any]


@dataclass(frozen=True)
class Enriched:
    cards: dict[str, Any]
    images: dict[str, bytes]


# ---- candidates ------------------------------------------------------------------------------------------------------------------
def _clean(text: str) -> str:
    return _POSSESSIVE.sub("", _EDGE.sub("", text))


def place_candidates(tokens: Sequence[Any], limit: int = MAX_CANDIDATES) -> list[str]:
    """Runs of capitalised words as written in the passage ("Piedmont Park", "Catherine de Bourgh"), in order, without duplicates.

    A single capitalised word that starts a sentence is skipped ("Cities are big"): its capital only marks the sentence start.
    Abbreviations such as "Mr." end a run. Whatever this finds is only a candidate; the Wikipedia lookup decides what is a place."""
    runs: list[list[str]] = []
    run: list[str] = []
    run_starts_sentence = False
    previous_sentence = None

    def close() -> None:
        nonlocal run, run_starts_sentence
        if run:
            while run and run[-1].lower() in _CONNECTORS:
                run = run[:-1]
            if run and not (len(run) == 1 and run_starts_sentence) and len(" ".join(run)) > 1:
                runs.append(run)
                if run_starts_sentence and len(run) >= 2:
                    runs.append(run[1:])  # the first word may only be a capitalised sentence start ("Then Lady Catherine de Bourgh")
        run, run_starts_sentence = [], False

    for token in tokens:
        raw = token.text
        word = _clean(raw)
        first_in_sentence = token.sentence != previous_sentence
        previous_sentence = token.sentence
        if first_in_sentence:
            close()
        capital = bool(word) and word[0].isupper() and any(c.isalpha() for c in word) and not _ABBREVIATION.match(raw)
        connector = word.lower() in _CONNECTORS and bool(run)
        if capital or connector:
            if not run:
                run_starts_sentence = first_in_sentence
            run.append(word)
            if raw[-1:] in ",;:.!?)\"”—–" or raw != raw.rstrip():
                close()  # punctuation after the word ends the name
        else:
            close()
    close()
    seen: dict[str, None] = {}
    for found in runs:
        seen.setdefault(" ".join(found), None)
    return list(seen)[:limit]


def ner_places(text: str, nlp: Any = None) -> list[str]:
    """Places spaCy finds (countries, cities, landmarks, buildings, mountains, rivers), when spaCy and its model are installed.
    The generator image already ships both for Kokoro's grapheme-to-phoneme step, so this adds no dependency."""
    try:
        if nlp is None:
            import spacy

            nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])
        return [ent.text.strip() for ent in nlp(text).ents if ent.label_ in ("GPE", "LOC", "FAC") and ent.text.strip()]
    except Exception as err:  # noqa: BLE001 (a missing or broken model must never stop publishing)
        LOG.warning("place detection with spaCy skipped: %s", err)
        return []


# ---- the lookup ------------------------------------------------------------------------------------------------------------------
def fetch(url: str, binary: bool = False) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as res:  # noqa: S310 (fixed Wikimedia https hosts)
        body = res.read(MAX_BYTES + 1 if binary else 2_000_000)
    if binary:
        if len(body) > MAX_BYTES:
            raise ValueError("image is larger than the size cap")
        return body
    return json.loads(body.decode("utf-8"))


def _query(base: str, **params: str) -> str:
    return base + "?" + urllib.parse.urlencode({"action": "query", "format": "json", **params})


def _pages(reply: Any) -> dict[str, dict[str, Any]]:
    pages = reply.get("query", {}).get("pages") if isinstance(reply, dict) else None
    return {k: v for k, v in pages.items() if isinstance(v, dict)} if isinstance(pages, dict) else {}


def _resolve(title: str, query: dict[str, Any]) -> str:
    """Follow Wikipedia's own title normalisation and redirects, so "Britain" finds its final page."""
    for key in ("normalized", "redirects"):
        for step in query.get(key, []) or []:
            if isinstance(step, dict) and step.get("from") == title:
                title = step.get("to", title)
    return title


def _sentence(description: str) -> str:
    text = re.sub(r"\s+", " ", description).strip()
    text = text[:1].upper() + text[1:]
    return (text if text.endswith((".", "!", "?")) else text + ".")[:160]


def _real_places(candidates: list[str], http_get: HttpGet) -> dict[str, dict[str, Any]]:
    """candidate -> Wikipedia page, for candidates that are real, unambiguous places with a description. One request."""
    reply = http_get(_query(WIKIPEDIA, redirects="1", titles="|".join(candidates), prop="coordinates|pageprops|description|pageimages",
                            colimit="max", piprop="name", ppprop="disambiguation"))
    query = reply.get("query", {}) if isinstance(reply, dict) else {}
    by_title = {p.get("title"): p for p in _pages(reply).values()}
    found: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        page = by_title.get(_resolve(candidate, query))
        if not page or "missing" in page or "coordinates" not in page or "disambiguation" in (page.get("pageprops") or {}):
            continue
        if not isinstance(page.get("description"), str) or not page["description"].strip():
            continue  # never invent a summary
        found[candidate] = page
    return found


def _alt(description: Optional[str], name: str, summary: str) -> str:
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", description or "")).strip()
    if plain and len(plain) <= MAX_ALT and alt_problem(plain, name) is None:
        return plain
    fallback = f"Picture of {name}: {summary[:1].lower()}{summary[1:]}"
    return fallback if len(fallback) <= MAX_ALT else fallback[: MAX_ALT - 1].rstrip() + "…"


_UNHELPFUL = re.compile(
    r"flag|coat[ _]of[ _]arms|emblem|(?:^|[ _.-])seal(?:[ _.-]|$)|logo|icon|symbol|banner|signature|stamp|crest|wordmark|ambox|edit-|"
    r"question|padlock|disambig|commons-|wikt|portal|\.(?:ogg|oga|webm|pdf|tiff?|gif)$", re.IGNORECASE)
_ALLOWED_FILE = re.compile(r"\.(?:jpe?g|png|svg)$", re.IGNORECASE)
_MAP_NAME = re.compile(r"orthographic|locator|location|globe|\bmap\b|_map|map_", re.IGNORECASE)
_BIG_PLACE = re.compile(r"\b(?:country|continent|state|island|province|territory|region|nation)\b", re.IGNORECASE)
_MIN_WIDTH = 300
ALTERNATES_PER_PLACE = 12


def _norm_file(name: str) -> str:
    return name.removeprefix("File:").replace("_", " ").strip()


def _commons_infos(files: list[str], http_get: HttpGet) -> dict[str, dict[str, Any]]:
    """Commons image info (size, type, licence, thumbnail) for many files, 40 per request."""
    out: dict[str, dict[str, Any]] = {}
    unique = list(dict.fromkeys(files))
    for start in range(0, len(unique), 40):
        reply = http_get(_query(COMMONS, prop="imageinfo", iiprop="url|size|mime|extmetadata", iiurlwidth=str(THUMB_WIDTH),
                                iiextmetadatafilter="LicenseShortName|Artist|ImageDescription",
                                titles="|".join("File:" + f for f in unique[start:start + 40])))
        for page in _pages(reply).values():
            info = (page.get("imageinfo") or [None])[0]
            if isinstance(info, dict):
                out[_norm_file(str(page.get("title", "")))] = info
    return out


def _usable(file_name: str, info: Optional[dict[str, Any]], prefer_map: bool = False) -> Optional[int]:
    """None if this picture may not be used, otherwise its preference rank: photo (0) before PNG (1) before a map drawn as SVG (2).
    Flags, emblems and logos are never used. An SVG original is fine only because Commons serves a PNG thumbnail of it; the bytes are
    checked again after download."""
    if not info or _UNHELPFUL.search(file_name) or not _ALLOWED_FILE.search(file_name) or not info.get("thumburl"):
        return None
    meta = info.get("extmetadata") or {}
    if not license_ok((meta.get("LicenseShortName") or {}).get("value")):
        return None
    mime = info.get("mime")
    if mime not in ("image/jpeg", "image/png", "image/svg+xml"):
        return None
    if mime != "image/svg+xml" and int(info.get("width") or 0) < _MIN_WIDTH:
        return None
    if prefer_map and _MAP_NAME.search(file_name):
        return -1  # a location map is the best picture of a country, state or continent
    return {"image/jpeg": 0, "image/png": 1, "image/svg+xml": 2}[mime]


def _prefers_map(description: Optional[str]) -> bool:
    """Countries, states, continents and islands are best shown on a location map: a photo of "China" is whatever the article happens to
    contain (a portrait, a bird). Cities, landmarks, parks and rivers get photographs."""
    return bool(description and _BIG_PLACE.search(description))


def _map_names(title: str) -> list[str]:
    """Standard Commons location-map file names for a place. A title with a qualifier ("Georgia (U.S. state)") must NEVER use the plain-name
    maps: "Georgia (orthographic projection).svg" is the country in the Caucasus, a different place. Only US states are handled specially."""
    short, _, qualifier = title.partition(" (")
    short = short.strip()
    if qualifier:
        return [f"{short} in United States.svg"] if qualifier.lower().startswith("u.s. state") else []
    return [f"{short} (orthographic projection).svg", f"Location {short}.svg", f"{short} in the world.svg"]


def _article_images(titles: list[str], http_get: HttpGet) -> dict[str, list[str]]:
    reply = http_get(_query(WIKIPEDIA, redirects="1", titles="|".join(titles), prop="images", imlimit="max"))
    query = reply.get("query", {}) if isinstance(reply, dict) else {}
    out: dict[str, list[str]] = {}
    for page in _pages(reply).values():
        files = [_norm_file(str(i.get("title", ""))) for i in (page.get("images") or []) if isinstance(i, dict)]
        out[str(page.get("title"))] = [f for f in files if f and not _UNHELPFUL.search(f) and _ALLOWED_FILE.search(f)]
    return out


def _pictures(pages: dict[str, dict[str, Any]], passage_id: str, http_get: HttpGet, out_of_time: Callable[[], bool]) -> tuple[dict[str, dict[str, Any]], dict[str, bytes], dict[str, dict[str, str]]]:
    """A licence-gated small picture for every place that has ANY usable one: the article's lead image first, then its other pictures
    (photos before maps). A place is text-only only when nothing in its whole article qualifies."""
    if out_of_time():
        return {}, {}, {}
    leads = {name: _norm_file(page["pageimage"]) for name, page in pages.items() if isinstance(page.get("pageimage"), str)}
    wants_map = {name: _prefers_map(page.get("description")) for name, page in pages.items()}
    # Commons names its location maps in a standard way, so for countries, states and continents try those names directly.
    probes = {name: _map_names(str(pages[name]["title"])) for name in pages if wants_map[name]}
    infos = _commons_infos([*leads.values(), *(f for files in probes.values() for f in files)], http_get) if (leads or probes) else {}
    ranked: dict[str, list[tuple[int, int, str]]] = {name: [] for name in pages}
    for name, file_name in leads.items():
        rank = _usable(file_name, infos.get(file_name), wants_map[name])
        if rank is not None:
            ranked[name].append((rank, 0, file_name))
    for name, files in probes.items():
        for file_name in files:
            rank = _usable(file_name, infos.get(file_name), True)
            if rank is not None:
                ranked[name].append((rank, 0, file_name))
    needy = [name for name in pages if not ranked[name]]
    if needy and not out_of_time():
        by_title = _article_images([str(pages[n]["title"]) for n in needy], http_get)
        extra = {n: by_title.get(str(pages[n]["title"]), [])[:ALTERNATES_PER_PLACE] for n in needy}
        more = _commons_infos([f for files in extra.values() for f in files if f not in infos], http_get)
        infos.update(more)
        for name, files in extra.items():
            for order, file_name in enumerate(files, start=1):
                rank = _usable(file_name, infos.get(file_name), wants_map[name])
                if rank is not None:
                    ranked[name].append((rank, order, file_name))
    cards: dict[str, dict[str, Any]] = {}
    images: dict[str, bytes] = {}
    sources: dict[str, dict[str, str]] = {}  # where each picture came from (for people who review it)
    for name in pages:
        if len(images) >= MAX_IMAGES or out_of_time():
            break
        for _, _, file_name in sorted(ranked[name])[:3]:  # best first; a download that fails the byte check falls to the next one
            info = infos[file_name]
            try:
                data = http_get(info["thumburl"], binary=True)
            except (OSError, ValueError) as err:
                LOG.info("picture for %s skipped: %s", name, err)
                continue
            if image_ext(data) is None:
                continue
            meta = info.get("extmetadata") or {}
            licence = str(meta["LicenseShortName"]["value"]).strip()
            file = target_name(passage_id, name, data)
            images[file] = data
            width, height = image_size(data) or (None, None)
            summary = _sentence(pages[name]["description"])
            artist = clean_artist((meta.get("Artist") or {}).get("value"))
            credit = credit_line(artist, licence)
            if info.get("mime") == "image/svg+xml":
                credit = credit.replace("Photo:", "Image:", 1)  # a map, not a photograph
            sources[name] = {"file": file_name, "artist": artist, "license": licence, "page": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(file_name.replace(" ", "_"))}
            cards[name] = {"imageUrl": f"/data/{file}", "imageWidth": width, "imageHeight": height,
                           "imageAlt": _alt((meta.get("ImageDescription") or {}).get("value"), name, summary), "imageCredit": credit}
            break
    return cards, images, sources


def _switched_off(passage: dict[str, Any]) -> bool:
    """A teacher can turn place lookups off for one passage (settings.placeCards false), or an operator for the whole deployment (PLACE_CARDS=off)."""
    return os.environ.get("PLACE_CARDS", "").strip().lower() in ("off", "0", "false", "no") or (passage.get("settings") or {}).get("placeCards") is False


def enrich_places(
    passage: dict[str, Any], http_get: HttpGet = fetch, budget_s: float = BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic, ner: Optional[Callable[[str], list[str]]] = None,
) -> Optional[Enriched]:
    """Cards for the real places in an English, teacher-generated passage, or None. Never raises."""
    if passage.get("source") != "generated" or (passage.get("language") or "en") != "en" or _switched_off(passage):
        return None
    try:
        tokens = tokenize_html(passage.get("content") or "")
        plain = " ".join(t.text for t in tokens)
        if ner is None:
            candidates = place_candidates(tokens, MAX_CANDIDATES)  # tools and tests only: production always passes a place detector
        else:
            # PRIVACY: with a detector, only the names of places it finds are ever sent to Wikipedia. Other capitalised words (people,
            # schools, anything) never leave the generator, and if the detector is unavailable nothing is sent at all.
            candidates = []
            for extra in ner(plain):
                extra = re.sub(r"^(?:the)\s+", "", _clean(extra), flags=re.IGNORECASE)  # "the River Thames" is the place "River Thames"
                if extra and extra not in candidates and re.search(rf"(?<!\w){re.escape(extra)}(?!\w)", plain):
                    candidates.append(extra)
            candidates = candidates[:MAX_CANDIDATES]
        if not candidates:
            return None
        started = clock()
        out_of_time = lambda: clock() - started > budget_s  # noqa: E731
        pages = _real_places(candidates, http_get)
        if not pages:
            return None
        pictures, images, _ = _pictures(pages, passage["uuid"], http_get, out_of_time)
        places = {
            name: {"name": name, "summary": _sentence(page["description"]), "attribution": "Wikipedia, CC BY-SA",
                   "imageUrl": None, "imageAlt": None, "imageCredit": None, "imageWidth": None, "imageHeight": None, **pictures.get(name, {})}
            for name, page in pages.items()
        }
        return Enriched({"words": {}, "places": places, "reviewed": False, "source": "wikipedia"}, images)
    except Exception as err:  # noqa: BLE001 (live path: log and carry on, audio must still publish)
        LOG.warning("place enrichment skipped: %s", err)
        return None


def write_enriched(data_dir: Path, passage_id: str, enriched: Enriched) -> list[str]:
    """Write the cards and pictures into data_dir. A cards document a person already reviewed is never replaced."""
    target = data_dir / f"{passage_id}.cards.json"
    try:
        if target.exists() and json.loads(target.read_text(encoding="utf-8")).get("reviewed") is True:
            return []
    except (OSError, ValueError):
        pass
    data_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in enriched.images.items():
        if NAME_PATTERN.fullmatch(name):
            (data_dir / name).write_bytes(data)
            written.append(name)
    target.write_text(json.dumps(enriched.cards, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return [target.name, *written]
