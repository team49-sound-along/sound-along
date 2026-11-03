"""Place images: licence gate, credit text, raster check, file naming and the apply step. No network."""
import hashlib
import json

import pytest

import place_images as pi

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.mark.parametrize("name", ["CC BY-SA 4.0", "CC BY 2.5", "CC BY-SA 3.0", "CC0", "CC0 1.0", "Public domain", "Public Domain", "PD-USGov", "CC BY 4.0"])
def test_free_licences_are_accepted(name):
    assert pi.license_ok(name)


@pytest.mark.parametrize("name", [None, "", "All rights reserved", "CC BY-NC 4.0", "CC BY-NC-SA 3.0", "CC BY-ND 4.0", "GFDL", "Fair use", "unknown"])
def test_everything_else_is_refused_including_non_commercial_and_no_derivatives(name):
    assert not pi.license_ok(name)


def test_artist_html_is_stripped_capped_and_has_a_fallback():
    assert pi.clean_artist('<a href="//commons.wikimedia.org/wiki/User:X" title="User:X">Frank Schulenburg</a>') == "Frank Schulenburg"
    assert pi.clean_artist("A" * 300) == "A" * 80
    assert pi.clean_artist(None) == "Unknown author" and pi.clean_artist("<b></b>") == "Unknown author"
    assert "<" not in pi.clean_artist("x <script>alert(1)</script> y")


def test_credit_line_names_the_author_the_licence_and_commons():
    line = pi.credit_line("Frank Schulenburg", "CC BY-SA 4.0")
    assert line == "Photo: Frank Schulenburg, CC BY-SA 4.0, via Wikimedia Commons"
    assert pi.credit_line("USGS", "Public domain") == "Image: USGS, Public domain, via Wikimedia Commons"


def test_only_real_jpeg_and_png_bytes_are_accepted_never_svg_or_html():
    assert pi.image_ext(JPEG) == "jpg" and pi.image_ext(PNG) == "png"
    for bad in (b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", b"<html>", b"GIF89a", b"", b"\xff\xd8"):
        assert pi.image_ext(bad) is None


def test_file_names_carry_a_content_hash_and_match_the_serving_allow_list():
    name = pi.target_name("2b781dab-4521-40d2-a9b6-ad5f2bb0ba98", "Piedmont Park", JPEG)
    digest = hashlib.sha256(JPEG).hexdigest()[:8]
    assert name == f"2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.place-piedmont-park-{digest}.jpg"
    assert pi.NAME_PATTERN.fullmatch(name)
    assert not pi.NAME_PATTERN.fullmatch("../x.jpg") and not pi.NAME_PATTERN.fullmatch("a.place-x-12345678.svg")


def test_slug_is_safe_for_any_place_name():
    assert pi.slug("Piedmont Park") == "piedmont-park" and pi.slug("St. John's / Bay!") == "st-john-s-bay"
    assert pi.slug("   ") == "place"


def test_alt_text_must_be_short_and_not_just_the_place_name():
    assert pi.alt_problem("A lake with a city skyline behind it.", "Piedmont Park") is None
    assert "125" in pi.alt_problem("x" * 126, "Piedmont Park")
    assert pi.alt_problem("Piedmont Park", "Piedmont Park") is not None
    assert pi.alt_problem("", "Piedmont Park") is not None
    assert pi.alt_problem("<b>hi</b>", "Piedmont Park") is not None


def test_apply_writes_the_image_into_the_cards_and_leaves_other_places_without_one(tmp_path):
    pid = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
    cards = tmp_path / "cards"
    (cards / "images.candidates").mkdir(parents=True)
    (cards / f"{pid}.cards.json").write_text(json.dumps({"words": {}, "places": {
        "Piedmont Park": {"name": "Piedmont Park", "summary": "s", "attribution": "Wikipedia, CC BY-SA", "imageUrl": None},
        "Atlanta": {"name": "Atlanta", "summary": "s", "attribution": "Wikipedia, CC BY-SA", "imageUrl": None}}}))
    (cards / "images.candidates" / "piedmont-park.jpg").write_bytes(JPEG)
    manifest = {"images": [{"passageId": pid, "place": "Piedmont Park", "candidate": "piedmont-park.jpg", "alt": "A lake with a city skyline behind it.",
                            "artist": "Frank Schulenburg", "license": "CC BY-SA 4.0", "page": "https://commons.wikimedia.org/wiki/File:X.jpg"}]}
    (cards / "images.json").write_text(json.dumps(manifest))
    written = pi.apply(cards)
    out = json.loads((cards / f"{pid}.cards.json").read_text())["places"]
    park, atlanta = out["Piedmont Park"], out["Atlanta"]
    assert park["imageUrl"].startswith(f"/data/{pid}.place-piedmont-park-") and park["imageUrl"].endswith(".jpg")
    assert park["imageAlt"] == "A lake with a city skyline behind it." and park["imageCredit"] == "Photo: Frank Schulenburg, CC BY-SA 4.0, via Wikimedia Commons"
    assert (atlanta["imageUrl"], atlanta["imageAlt"], atlanta["imageCredit"]) == (None, None, None)  # every place carries all three fields
    assert (cards / "images" / park["imageUrl"].rsplit("/", 1)[1]).read_bytes() == JPEG and len(written) == 1


def test_apply_refuses_a_candidate_that_is_not_a_real_image_or_has_a_bad_licence_or_alt(tmp_path):
    pid = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
    cards = tmp_path / "cards"
    (cards / "images.candidates").mkdir(parents=True)
    (cards / f"{pid}.cards.json").write_text(json.dumps({"words": {}, "places": {"Piedmont Park": {"name": "Piedmont Park"}}}))
    (cards / "images.candidates" / "x.jpg").write_bytes(b"<svg><script>1</script></svg>")
    base = {"passageId": pid, "place": "Piedmont Park", "candidate": "x.jpg", "alt": "A lake with a skyline.", "artist": "A", "license": "CC BY-SA 4.0", "page": "p"}
    for entry, message in (
        (base, "not a JPEG or PNG"),
        ({**base, "license": "CC BY-NC 4.0"}, "licence"),
        ({**base, "alt": ""}, "alt"),
    ):
        (cards / "images.json").write_text(json.dumps({"images": [entry]}))
        if message != "not a JPEG or PNG":
            (cards / "images.candidates" / "x.jpg").write_bytes(JPEG)
        with pytest.raises(ValueError, match=message):
            pi.apply(cards)


# ---- picture dimensions (so the reader can fit the picture and reserve its space) -----------------------------------------------
def _png(width, height):
    import struct

    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + b"\x00" * 4


def test_image_size_is_read_from_real_files():
    from pathlib import Path

    folder = Path(__file__).resolve().parent.parent / "samples" / "cards" / "images"
    sizes = {p.name.split(".place-")[1].rsplit("-", 1)[0]: pi.image_size(p.read_bytes()) for p in folder.glob("*.jpg")}
    assert sizes["piedmont-park"] == (500, 625) and sizes["great-britain"] == (500, 803) and sizes["london"] == (500, 281)


def test_image_size_for_png_and_for_bytes_that_are_not_images():
    assert pi.image_size(_png(640, 480)) == (640, 480)
    for bad in (b"", b"\xff\xd8\xff", b"\xff\xd8\xff\xe0" + b"0" * 10, b"\x89PNG\r\n\x1a\n", b"<svg>", JPEG):
        assert pi.image_size(bad) is None


def test_apply_stores_the_picture_size_and_places_without_a_picture_get_none(tmp_path):
    pid = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"
    cards = tmp_path / "cards"
    (cards / "images.candidates").mkdir(parents=True)
    (cards / f"{pid}.cards.json").write_text(json.dumps({"words": {}, "places": {"Piedmont Park": {"name": "Piedmont Park"}, "Atlanta": {"name": "Atlanta"}}}))
    (cards / "images.candidates" / "piedmont-park.png").write_bytes(_png(500, 625))
    (cards / "images.json").write_text(json.dumps({"images": [{"passageId": pid, "place": "Piedmont Park", "candidate": "piedmont-park.png",
        "alt": "A lake with a skyline.", "artist": "A", "license": "CC0", "page": "p"}]}))
    pi.apply(cards)
    out = json.loads((cards / f"{pid}.cards.json").read_text())["places"]
    assert (out["Piedmont Park"]["imageWidth"], out["Piedmont Park"]["imageHeight"]) == (500, 625)
    assert (out["Atlanta"]["imageWidth"], out["Atlanta"]["imageHeight"]) == (None, None)


def test_a_map_is_credited_as_an_image_not_a_photo_even_under_cc_by_sa():
    assert pi.credit_line("Domob", "CC BY-SA 3.0", kind="Image") == "Image: Domob, CC BY-SA 3.0, via Wikimedia Commons"
    assert pi.credit_line("Domob", "CC BY-SA 3.0") == "Photo: Domob, CC BY-SA 3.0, via Wikimedia Commons"
