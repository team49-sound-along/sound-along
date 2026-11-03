import copy
import json

import pytest

import merge_product_json as m

PRODUCT = {"uuid": "p1", "title": "Park", "au": "Park_audio_file", "features": ["au", "hau", "qsmw"], "extra": {"keep": True}}
BLOCK = {"soundAlong": {"version": 1, "passageId": "p1", "defaultVoice": "human", "voices": [{"kind": "human", "audio": "h1"}, {"kind": "ai", "audio": "p1"}]},
         "features": ["sa", "sahv"]}


def test_adds_the_block_and_flags_without_touching_other_fields():
    out = m.merge(PRODUCT, BLOCK)
    assert out["features"] == ["au", "hau", "qsmw", "sa", "sahv"]
    assert out["au"] == "Park_audio_file" and out["extra"] == {"keep": True}
    assert out["soundAlong"]["defaultVoice"] == "human"


def test_does_not_mutate_the_input_and_never_duplicates_a_flag():
    snapshot = copy.deepcopy(PRODUCT)
    once = m.merge(PRODUCT, BLOCK)
    twice = m.merge(once, BLOCK)
    assert PRODUCT == snapshot
    assert twice["features"] == once["features"]


def test_a_product_without_features_still_merges():
    out = m.merge({"uuid": "p1"}, BLOCK)
    assert out["features"] == ["sa", "sahv"]


def test_a_block_for_another_passage_is_refused():
    with pytest.raises(ValueError, match="passage p1"):
        m.merge({"uuid": "other"}, BLOCK)


def test_cli_writes_the_merged_file_and_reports_a_missing_block(tmp_path, capsys):
    (tmp_path / "product.json").write_text(json.dumps(PRODUCT))
    assert m.main([str(tmp_path / "product.json"), "--data", str(tmp_path)]) == 1  # no block yet
    (tmp_path / "p1.soundalong.json").write_text(json.dumps(BLOCK))
    assert m.main([str(tmp_path / "product.json"), "--data", str(tmp_path), "-o", str(tmp_path / "out.json")]) == 0
    assert json.loads((tmp_path / "out.json").read_text())["features"][-1] == "sahv"
