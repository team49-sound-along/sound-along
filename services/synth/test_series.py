"""Series metadata for the parts of a long document: only a well-formed description is ever stored."""
import json

import pytest

from series import clean_series

IDS = [f"2b781dab-4521-40d2-a9b6-ad5f2bb0ba9{i}" for i in range(3)]
SERIES = {"id": "5af24980-4d6d-41c1-87fa-4f21cb2d169d", "index": 2, "total": 3, "title": "The Story", "partIds": IDS}


def test_a_valid_description_is_kept_and_copied():
    out = clean_series(SERIES)
    assert out == SERIES and out is not SERIES and out["partIds"] is not SERIES["partIds"]


@pytest.mark.parametrize("bad", [
    None, "x", [], {}, {**SERIES, "partIds": IDS[:1]}, {**SERIES, "partIds": IDS + ["not-a-uuid"]}, {**SERIES, "total": 2}, {**SERIES, "index": 0},
    {**SERIES, "index": 4}, {**SERIES, "index": "2"}, {**SERIES, "id": "nope"}, {**SERIES, "partIds": "abc"},
])
def test_anything_else_is_ignored(bad):
    assert clean_series(bad) is None


def test_the_title_is_capped_and_a_missing_title_is_empty():
    assert len(clean_series({**SERIES, "title": "x" * 500})["title"]) == 120
    assert clean_series({**SERIES, "title": None})["title"] == ""


def test_too_many_parts_are_refused():
    ids = [f"2b781dab-4521-40d2-a9b6-{i:012x}" for i in range(41)]
    assert clean_series({**SERIES, "partIds": ids, "total": 41}) is None

