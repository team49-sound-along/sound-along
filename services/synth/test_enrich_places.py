"""Live place enrichment for ANY uploaded passage: candidates, one batched Wikipedia lookup, a licence-gated picture, never a crash."""
import json
import urllib.error
import urllib.parse

import pytest

import enrich_places as ep
from pipeline import tokenize_html  # noqa: F401  (pipeline puts services/parse on the path)

PID = "0e8b1b1e-1111-4222-8333-444455556666"
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 200


def tokens(html):
    return tokenize_html(html)


# ---- candidates ------------------------------------------------------------------------------------------------------------------
def test_candidates_are_runs_of_capitalised_words_as_written_in_the_passage():
    t = tokens("<p>We went to Piedmont Park in Atlanta, Georgia. Then Lady Catherine de Bourgh spoke. Mr. Collins left.</p>")
    got = ep.place_candidates(t)
    assert "Piedmont Park" in got and "Atlanta" in got and "Georgia" in got and "Lady Catherine de Bourgh" in got
    assert "Mr." not in got and "Then" not in got and "We" not in got


def test_a_single_capitalised_word_at_the_start_of_a_sentence_is_not_a_candidate_but_a_multi_word_name_is():
    t = tokens("<p>Cities are big. Times Square is loud. Every day we walk.</p>")
    got = ep.place_candidates(t)
    assert "Times Square" in got and "Cities" not in got and "Every" not in got


def test_possessives_and_edge_punctuation_are_stripped_and_candidates_are_unique_and_capped():
    t = tokens("<p>I like Boston’s parks, and \"London\" too. I saw Boston again and London again.</p>")
    assert ep.place_candidates(t) == ["Boston", "London"]
    many = "<p>" + " ".join(f"x Place{c}{c}" for c in "abcdefghijklmnopqrstuvwxyz") + "</p>"
    assert len(ep.place_candidates(tokens(many), limit=5)) == 5


def test_every_candidate_is_text_that_really_appears_in_the_passage():
    t = tokens("<p>She visited Tower Bridge, then Mount Everest in Nepal.</p>")
    plain = " ".join(x.text for x in t)
    for c in ep.place_candidates(t):
        assert c in plain


# ---- the lookup ------------------------------------------------------------------------------------------------------------------
def wiki(pages, redirects=None, normalized=None):
    q = {"pages": {str(i): p for i, p in enumerate(pages)}}
    if redirects:
        q["redirects"] = [{"from": a, "to": b} for a, b in redirects]
    if normalized:
        q["normalized"] = [{"from": a, "to": b} for a, b in normalized]
    return {"query": q}


def commons(title, license_name="CC BY-SA 4.0", mime="image/jpeg", description="A lake with a city skyline", artist='<a href="x">Jane Doe</a>'):
    meta = {"LicenseShortName": {"value": license_name}, "Artist": {"value": artist}}
    if description is not None:
        meta["ImageDescription"] = {"value": description}
    return {"title": "File:" + title, "imageinfo": [{"mime": mime, "width": 800, "height": 600, "thumburl": f"https://upload.wikimedia.org/thumb/{title}", "extmetadata": meta}]}


class FakeHttp:
    def __init__(self, wikipedia, commons_pages=None, image=JPEG, fail=None):
        self.wikipedia, self.commons_pages, self.image, self.fail, self.urls = wikipedia, commons_pages or [], image, fail, []

    def __call__(self, url, binary=False):
        self.urls.append(url)
        if self.fail:
            raise self.fail
        if binary:
            return self.image
        if "en.wikipedia.org" in url:
            return self.wikipedia
        return {"query": {"pages": {str(i): p for i, p in enumerate(self.commons_pages)}}}


PARK = {"title": "Piedmont Park", "coordinates": [{"lat": 1, "lon": 2}], "description": "Urban park in Atlanta, Georgia", "pageimage": "Lake.jpg"}
PASSAGE = {"uuid": PID, "language": "en", "source": "generated", "content": "<p>Over six million people visit Piedmont Park in Atlanta every year. Doug Widener works there.</p>"}


def test_only_real_places_with_a_description_become_cards_and_everything_is_one_batched_query():
    pages = [PARK, {"title": "Atlanta", "coordinates": [{}], "description": "Capital of Georgia, U.S."},
             {"title": "Doug Widener", "missing": ""},
             {"title": "Georgia", "pageprops": {"disambiguation": ""}, "description": "Topics referred to by the same term"},
             {"title": "Charlotte", "coordinates": [{}], "pageprops": {"disambiguation": ""}, "description": "x"},
             {"title": "Berlin", "coordinates": [{}]}]  # no description: skipped rather than invented
    http = FakeHttp(wiki(pages), [commons("Lake.jpg")])
    passage = {**PASSAGE, "content": "<p>We saw Piedmont Park, Atlanta, Doug Widener, Georgia, Charlotte and Berlin.</p>"}
    out = ep.enrich_places(passage, http)
    assert sorted(out.cards["places"]) == ["Atlanta", "Piedmont Park"]
    assert sum("en.wikipedia.org" in u and "coordinates" in u for u in http.urls) == 1  # ONE batched place lookup, not one request per place
    q = urllib.parse.parse_qs(urllib.parse.urlparse(http.urls[0]).query)
    assert q["redirects"] == ["1"] and set(q["titles"][0].split("|")) >= {"Piedmont Park", "Atlanta", "Georgia"}


def test_a_card_has_the_contract_fields_a_description_summary_and_is_marked_unreviewed():
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]))
    card = out.cards["places"]["Piedmont Park"]
    assert set(card) == {"name", "summary", "attribution", "imageUrl", "imageAlt", "imageCredit", "imageWidth", "imageHeight"}
    assert card["summary"] == "Urban park in Atlanta, Georgia." and card["attribution"] == "Wikipedia, CC BY-SA"
    assert out.cards["words"] == {} and out.cards["reviewed"] is False and out.cards["source"] == "wikipedia"


def test_the_picture_is_stored_under_a_hashed_name_with_alt_text_and_a_credit():
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]))
    card = out.cards["places"]["Piedmont Park"]
    name = card["imageUrl"].removeprefix("/data/")
    assert ep.NAME_PATTERN.fullmatch(name) and name.startswith(PID + ".place-piedmont-park-") and out.images[name] == JPEG
    assert card["imageAlt"] == "A lake with a city skyline" and card["imageCredit"] == "Photo: Jane Doe, CC BY-SA 4.0, via Wikimedia Commons"


def test_alt_text_falls_back_to_the_description_when_commons_has_none_or_too_long():
    for description in (None, "x" * 300, "<p></p>"):
        out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg", description=description)]))
        alt = out.cards["places"]["Piedmont Park"]["imageAlt"]
        assert alt == "Picture of Piedmont Park: urban park in Atlanta, Georgia." and len(alt) <= 125


@pytest.mark.parametrize("kwargs,why", [({"license_name": "CC BY-NC 4.0"}, "non-commercial"), ({"license_name": "GFDL"}, "gfdl"), ({"mime": "image/gif"}, "gif")])
def test_a_picture_that_fails_the_gate_leaves_a_text_only_card(kwargs, why):
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg", **kwargs)]))
    card = out.cards["places"]["Piedmont Park"]
    assert (card["imageUrl"], card["imageAlt"], card["imageCredit"]) == (None, None, None) and out.images == {}


def test_downloaded_bytes_that_are_not_a_real_image_are_never_stored():
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")], image=b"<svg><script>1</script></svg>"))
    assert out.cards["places"]["Piedmont Park"]["imageUrl"] is None and out.images == {}


def test_redirects_and_normalisation_are_followed_to_the_final_page():
    page = {"title": "United Kingdom", "coordinates": [{}], "description": "Country in Europe"}
    out = ep.enrich_places({**PASSAGE, "content": "<p>We love the UK a lot. We saw Britain today.</p>"}, FakeHttp(wiki([page], redirects=[("Britain", "United Kingdom")])))
    assert list(out.cards["places"]) == ["Britain"] and out.cards["places"]["Britain"]["name"] == "Britain"


# ---- live-safety -----------------------------------------------------------------------------------------------------------------
def test_offline_or_blocked_networks_give_nothing_and_never_raise():
    for error in (urllib.error.URLError("no network"), TimeoutError("slow"), ConnectionResetError("reset"), json.JSONDecodeError("bad", "x", 0)):
        assert ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), fail=error)) is None


def test_garbage_replies_are_survived():
    for reply in ({}, {"query": {}}, {"query": {"pages": "nope"}}, {"query": {"pages": {"1": "str"}}}, []):
        assert ep.enrich_places(PASSAGE, FakeHttp(reply)) is None


def test_a_passage_with_no_places_or_not_english_or_not_generated_is_skipped_without_any_request():
    http = FakeHttp(wiki([PARK]))
    assert ep.enrich_places({**PASSAGE, "content": "<p>the cat sat on the mat.</p>"}, http) is None and http.urls == []
    assert ep.enrich_places({**PASSAGE, "language": "es"}, http) is None
    assert ep.enrich_places({**PASSAGE, "source": "sample"}, http) is None and http.urls == []


def test_the_time_budget_stops_further_downloads_but_keeps_the_text_cards():
    ticks = iter([0.0])  # the first reading starts the budget; every later reading is far past it
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]), budget_s=10, clock=lambda: next(ticks, 99.0))
    assert out is not None and out.cards["places"]["Piedmont Park"]["imageUrl"] is None


def test_at_most_a_few_pictures_are_downloaded_per_passage():
    pages = [{"title": f"Place{c}", "coordinates": [{}], "description": "A town", "pageimage": f"{c}.jpg"} for c in "ABCDEFGHIJ"]
    http = FakeHttp(wiki(pages), [commons(f"{c}.jpg") for c in "ABCDEFGHIJ"])
    out = ep.enrich_places({**PASSAGE, "content": "<p>We saw " + " and ".join(f"Place{c}" for c in "ABCDEFGHIJ") + ".</p>"}, http)
    assert len(out.images) <= ep.MAX_IMAGES == 10


def test_write_enriched_puts_the_cards_and_pictures_in_the_data_folder_and_never_replaces_reviewed_cards(tmp_path):
    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]))
    written = ep.write_enriched(tmp_path, PID, out)
    assert f"{PID}.cards.json" in written and any(".place-piedmont-park-" in n for n in written)
    assert json.loads((tmp_path / f"{PID}.cards.json").read_text())["reviewed"] is False
    (tmp_path / f"{PID}.cards.json").write_text(json.dumps({"words": {}, "places": {}, "reviewed": True}))
    assert ep.write_enriched(tmp_path, PID, out) == []  # a person-reviewed document is never overwritten
    assert json.loads((tmp_path / f"{PID}.cards.json").read_text())["reviewed"] is True


def test_a_place_after_a_capitalised_sentence_opener_is_still_found():
    got = ep.place_candidates(tokens("<p>Then Paris was lovely. Soon London called.</p>"))
    assert "Paris" in got and "London" in got


# ---- the local publish path (the demo app's upload) -----------------------------------------------------------------------------
def test_run_local_writes_cards_for_a_generated_passage_and_survives_failures(tmp_path):
    import run_local

    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]))
    assert run_local.publish_cards({**PASSAGE, "source": "generated"}, tmp_path, lambda p: out) is True
    assert (tmp_path / f"{PID}.cards.json").exists() and any(".place-piedmont-park-" in f.name for f in tmp_path.iterdir())

    def boom(passage):
        raise RuntimeError("offline")

    assert run_local.publish_cards(PASSAGE, tmp_path / "other", boom) is False  # never raises
    assert run_local.publish_cards(PASSAGE, tmp_path / "none", lambda p: None) is False


def sent_titles(http):
    first = next(u for u in http.urls if "en.wikipedia.org" in u)
    return urllib.parse.parse_qs(urllib.parse.urlparse(first).query)["titles"][0].split("|")


def test_with_a_place_detector_only_places_it_finds_are_ever_sent_never_other_capitalised_words_or_names():
    passage = {**PASSAGE, "content": "<p>Maya and Daniel Smith visited London with Ms Rivera. Then Maya saw Berlin.</p>"}
    pages = [{"title": "London", "coordinates": [{}], "description": "Capital of England"}, {"title": "Berlin", "coordinates": [{}], "description": "Capital of Germany"}]
    http = FakeHttp(wiki(pages))
    out = ep.enrich_places(passage, http, ner=lambda text: ["London", "Berlin"])
    assert sent_titles(http) == ["London", "Berlin"]  # no "Maya", "Daniel Smith" or "Rivera" ever leaves the generator
    assert sorted(out.cards["places"]) == ["Berlin", "London"]


def test_if_the_detector_finds_nothing_or_is_unavailable_nothing_is_sent_at_all():
    http = FakeHttp(wiki([PARK]))
    assert ep.enrich_places(PASSAGE, http, ner=lambda text: []) is None and http.urls == []


def test_detector_places_lose_a_leading_the_are_unique_and_must_really_appear_in_the_text():
    passage = {**PASSAGE, "content": "<p>They ate lunch near the River Thames, then went to Lake Windermere.</p>"}
    http = FakeHttp(wiki([{"title": "River Thames", "coordinates": [{}], "description": "River in England"},
                          {"title": "Lake Windermere", "coordinates": [{}], "description": "Lake in England"}]))
    out = ep.enrich_places(passage, http, ner=lambda text: ["the River Thames", "The Lake Windermere", "Lake Windermere", "Atlantis"])
    assert sorted(sent_titles(http)) == ["Lake Windermere", "River Thames"] and sorted(out.cards["places"]) == ["Lake Windermere", "River Thames"]


def test_a_teacher_can_switch_place_lookups_off_for_a_passage_or_the_whole_deployment(monkeypatch):
    http = FakeHttp(wiki([PARK]))
    assert ep.enrich_places({**PASSAGE, "settings": {"placeCards": False}}, http, ner=lambda t: ["Piedmont Park"]) is None and http.urls == []
    monkeypatch.setenv("PLACE_CARDS", "off")
    assert ep.enrich_places(PASSAGE, http, ner=lambda t: ["Piedmont Park"]) is None and http.urls == []
    monkeypatch.delenv("PLACE_CARDS")
    assert ep.enrich_places({**PASSAGE, "settings": {"placeCards": True}}, FakeHttp(wiki([PARK])), ner=lambda t: ["Piedmont Park"]) is not None


# ---- the local publish path (the demo app's upload) -----------------------------------------------------------------------------
def test_run_local_writes_cards_for_a_generated_passage_and_survives_failures(tmp_path):
    import run_local

    out = ep.enrich_places(PASSAGE, FakeHttp(wiki([PARK]), [commons("Lake.jpg")]))
    assert run_local.publish_cards({**PASSAGE, "source": "generated"}, tmp_path, lambda p: out) is True
    assert (tmp_path / f"{PID}.cards.json").exists() and any(".place-piedmont-park-" in f.name for f in tmp_path.iterdir())

    def boom(passage):
        raise RuntimeError("offline")

    assert run_local.publish_cards(PASSAGE, tmp_path / "other", boom) is False  # never raises
    assert run_local.publish_cards(PASSAGE, tmp_path / "none", lambda p: None) is False


def test_spacy_places_are_added_without_a_leading_the_and_never_duplicate_a_run_we_already_found():
    passage = {**PASSAGE, "content": "<p>They ate lunch near the River Thames, then went to Lake Windermere.</p>"}
    pages = [{"title": "River Thames", "coordinates": [{}], "description": "River in England"},
             {"title": "Lake Windermere", "coordinates": [{}], "description": "Lake in England"}]
    http = FakeHttp(wiki(pages))
    out = ep.enrich_places(passage, http, ner=lambda text: ["the River Thames", "The Lake Windermere", "Lake Windermere"])
    assert sorted(out.cards["places"]) == ["Lake Windermere", "River Thames"]


# ---- never blank: SVG maps (rasterised by Commons), unhelpful lead images and the article's other pictures ----------------------------
class FakeWiki2(FakeHttp):
    """Also answers Wikipedia's `prop=images` (every picture used in an article) and serves PNG thumbnails for SVG originals."""

    def __init__(self, wikipedia, commons_pages=None, article_images=None, image=JPEG):
        super().__init__(wikipedia, commons_pages, image)
        self.article_images = article_images or {}

    def __call__(self, url, binary=False):
        if not binary and "en.wikipedia.org" in url and "prop=images" in url:
            self.urls.append(url)
            pages = [{"title": t, "images": [{"ns": 6, "title": "File:" + f} for f in files]} for t, files in self.article_images.items()]
            return {"query": {"pages": {str(i): p for i, p in enumerate(pages)}}}
        return super().__call__(url, binary)


PNG = b"\x89PNG\r\n\x1a\n" + b"p" * 100
ENGLAND = {"title": "England", "coordinates": [{}], "description": "Country in the United Kingdom", "pageimage": "Flag_of_England.svg"}
EPASSAGE = {**PASSAGE, "content": "<p>We went to England last year.</p>"}


def svg_info(title, license_name="Public domain", description="Location of England within Europe"):
    info = commons(title, license_name=license_name, mime="image/svg+xml", description=description)
    info["imageinfo"][0].update(width=800, height=600)
    return info


def test_an_svg_original_is_accepted_when_commons_serves_a_real_png_thumbnail_of_it():
    http = FakeWiki2(wiki([{**ENGLAND, "pageimage": "England_in_Europe_(orthographic_projection).svg"}]), [svg_info("England_in_Europe_(orthographic_projection).svg")], image=PNG)
    card = ep.enrich_places(EPASSAGE, http).cards["places"]["England"]
    assert card["imageUrl"].endswith(".png") and card["imageAlt"] == "Location of England within Europe"
    assert card["imageCredit"].startswith("Image: ")  # a map, not a photo


def test_a_flag_or_emblem_is_never_chosen_and_the_next_picture_in_the_article_is():
    infos = [svg_info("Flag_of_England.svg"), commons("Durham_Cathedral.jpg", description="Durham Cathedral from the river")]
    http = FakeWiki2(wiki([ENGLAND]), infos, article_images={"England": ["Flag_of_England.svg", "Coat_of_arms_of_England.svg", "Durham_Cathedral.jpg"]})
    out = ep.enrich_places(EPASSAGE, http)
    assert out.cards["places"]["England"]["imageAlt"] == "Durham Cathedral from the river" and len(out.images) == 1


def test_for_a_city_or_landmark_photos_are_preferred_over_maps():
    city = {"title": "Lakeville", "coordinates": [{}], "description": "City in Ohio, United States", "pageimage": "Flag_of_Lakeville.svg"}
    infos = [svg_info("Locator_map.svg"), commons("Skyline.jpg", description="The downtown skyline at dusk")]
    http = FakeWiki2(wiki([city]), infos, article_images={"Lakeville": ["Locator_map.svg", "Skyline.jpg"]})
    out = ep.enrich_places({**PASSAGE, "content": "<p>We drove to Lakeville.</p>"}, http, ner=lambda t: ["Lakeville"])
    assert out.cards["places"]["Lakeville"]["imageUrl"].endswith(".jpg")


def test_for_a_country_state_or_continent_a_location_map_beats_portraits_and_other_photos():
    infos = [commons("Henry_VIII_portrait.jpg", description="A king"), svg_info("England_in_Europe_(orthographic_projection).svg"), commons("Beach.jpg")]
    http = FakeWiki2(wiki([ENGLAND]), infos, article_images={"England": ["Henry_VIII_portrait.jpg", "Beach.jpg", "England_in_Europe_(orthographic_projection).svg"]})
    card = ep.enrich_places(EPASSAGE, http).cards["places"]["England"]
    assert card["imageUrl"].endswith(".jpg") is False or card["imageAlt"] == "Location of England within Europe"
    assert card["imageAlt"] == "Location of England within Europe"


def test_place_types_that_get_a_map_first():
    for d in ("Country in East Asia", "Continent in the Northern Hemisphere", "State of the United States", "Island country", "Region in Italy"):
        assert ep._prefers_map(d), d
    for d in ("Capital of England", "Urban park in Atlanta, Georgia", "Bridge over the Thames", "Earth's highest mountain", "Major river in Africa", "Ceremonial county in the East of England", "", None):
        assert not ep._prefers_map(d), d


def test_for_a_country_the_standard_commons_location_map_is_tried_by_name_even_when_the_article_lists_it_nowhere():
    infos = [commons("Some_Photo.jpg", description="A countryside view"), svg_info("England_(orthographic_projection).svg", description="England on a globe")]
    http = FakeWiki2(wiki([{**ENGLAND, "pageimage": "Some_Photo.jpg"}]), infos)
    card = ep.enrich_places(EPASSAGE, http).cards["places"]["England"]
    assert card["imageAlt"] == "England on a globe"
    commons_queries = " ".join(u for u in http.urls if "commons.wikimedia.org" in u)
    assert "England_%28orthographic_projection%29.svg" in commons_queries or "England+%28orthographic+projection%29.svg" in commons_queries


def test_a_lead_picture_with_a_bad_licence_falls_back_to_another_picture_of_the_article():
    lead = {**ENGLAND, "pageimage": "Lead.jpg"}
    infos = [commons("Lead.jpg", license_name="CC BY-NC 4.0"), commons("Other.jpg", description="A village green with a pond")]
    http = FakeWiki2(wiki([lead]), infos, article_images={"England": ["Lead.jpg", "Other.jpg"]})
    assert ep.enrich_places(EPASSAGE, http).cards["places"]["England"]["imageAlt"] == "A village green with a pond"


def test_a_place_stays_text_only_only_when_nothing_in_the_whole_article_qualifies():
    infos = [svg_info("Flag_of_England.svg"), commons("Bad.jpg", license_name="All rights reserved")]
    http = FakeWiki2(wiki([ENGLAND]), infos, article_images={"England": ["Flag_of_England.svg", "Bad.jpg", "Icon.svg", "Song.ogg"]})
    out = ep.enrich_places(EPASSAGE, http)
    assert out.cards["places"]["England"]["imageUrl"] is None and out.images == {}


def test_thumbnail_bytes_must_really_be_a_jpeg_or_png_even_for_an_svg():
    http = FakeWiki2(wiki([{**ENGLAND, "pageimage": "Map.svg"}]), [svg_info("Map.svg")], image=b"<svg><script>1</script></svg>")
    assert ep.enrich_places(EPASSAGE, http).cards["places"]["England"]["imageUrl"] is None


def test_every_one_of_many_places_can_get_a_picture_within_the_per_passage_limit():
    pages = [{"title": f"Place{c}", "coordinates": [{}], "description": "A town", "pageimage": f"{c}.jpg"} for c in "ABCDEFGHIJ"]
    out = ep.enrich_places({**PASSAGE, "content": "<p>We saw " + " and ".join(f"Place{c}" for c in "ABCDEFGHIJ") + ".</p>"},
                           FakeWiki2(wiki(pages), [commons(f"{c}.jpg") for c in "ABCDEFGHIJ"]))
    assert len(out.images) == ep.MAX_IMAGES == 10


def test_a_title_with_a_qualifier_never_borrows_the_map_of_its_namesake():
    """"Georgia (U.S. state)" must not get the standard map named just "Georgia", which is a different place (the country)."""
    assert ep._map_names("Georgia (U.S. state)") == ["Georgia in United States.svg"]
    assert ep._map_names("Georgia (country)") == []  # unknown qualifier: no guessing
    assert ep._map_names("Turkey (bird)") == []
    assert ep._map_names("China")[0] == "China (orthographic projection).svg"
    assert all("Georgia" not in n or n == "Georgia in United States.svg" for n in ep._map_names("Georgia (U.S. state)"))
