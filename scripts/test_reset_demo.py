import json

import reset_demo as r


def make(tmp_path):
    (tmp_path / "raw").mkdir()
    for pid, source in (("0e8b1b1e-0000-4000-8000-000000000001", "sample"), ("0e8b1b1e-0000-4000-8000-000000000002", "generated"), ("0e8b1b1e-0000-4000-8000-000000000003", None)):
        (tmp_path / "raw" / f"{pid}.json").write_text(json.dumps({"source": source} if source else {}))
        (tmp_path / f"{pid}.mp3").write_text("a")
        (tmp_path / f"{pid}.timing.json").write_text("{}")
    (tmp_path / "0e8b1b1e-0000-4000-8000-000000000002.cards.json").write_text("{}")
    state = {"assignments": [{"id": 1}], "events": {"plays": 5, "wordTaps": 3, "completions": 1}, "ratings": [{}, {}],
             "settings": {"voice": "af_heart"}, "pronunciations": {"gaieties": "gayetees"}}
    (tmp_path / "state.json").write_text(json.dumps(state))


def test_dry_run_lists_only_teacher_generated_passages_and_changes_nothing(tmp_path):
    make(tmp_path)
    before = {p.name: p.read_text() for p in tmp_path.rglob("*") if p.is_file()}
    current = r.plan(tmp_path)
    assert current["passages"] == ["0e8b1b1e-0000-4000-8000-000000000002"]
    assert sorted(p.name for p in current["files"]) == ["0e8b1b1e-0000-4000-8000-000000000002.cards.json", "0e8b1b1e-0000-4000-8000-000000000002.json", "0e8b1b1e-0000-4000-8000-000000000002.mp3", "0e8b1b1e-0000-4000-8000-000000000002.timing.json"]
    assert (current["assignments"], current["ratings"], current["events"]["plays"]) == (1, 2, 5)
    assert {p.name: p.read_text() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_apply_clears_traffic_and_generated_files_but_keeps_samples_and_settings(tmp_path):
    make(tmp_path)
    r.apply(tmp_path, r.plan(tmp_path))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["events"] == {"plays": 0, "wordTaps": 0, "completions": 0} and state["assignments"] == [] and "ratings" not in state
    assert state["settings"] == {"voice": "af_heart"} and state["pronunciations"] == {"gaieties": "gayetees"}
    assert not (tmp_path / "0e8b1b1e-0000-4000-8000-000000000002.mp3").exists() and not (tmp_path / "raw" / "0e8b1b1e-0000-4000-8000-000000000002.json").exists()
    assert (tmp_path / "0e8b1b1e-0000-4000-8000-000000000001.mp3").exists() and (tmp_path / "raw" / "0e8b1b1e-0000-4000-8000-000000000001.json").exists() and (tmp_path / "0e8b1b1e-0000-4000-8000-000000000003.mp3").exists()


def test_a_missing_data_folder_or_state_file_is_safe(tmp_path):
    current = r.plan(tmp_path)
    assert current["passages"] == [] and current["assignments"] == 0 and current["events"] == r.ZERO_EVENTS


UUID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98"


def test_a_sample_is_never_deleted_even_if_its_raw_file_says_generated(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / f"{UUID}.json").write_text(json.dumps({"source": "generated"}))
    (tmp_path / f"{UUID}.mp3").write_text("a")
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / f"{UUID}.json").write_text("{}")
    assert r.generated_ids(tmp_path, samples) == []


def test_only_uuid_named_raw_files_are_ever_candidates(tmp_path):
    (tmp_path / "raw").mkdir()
    for name in ("notes", "gen-one", "state-backup"):
        (tmp_path / "raw" / f"{name}.json").write_text(json.dumps({"source": "generated"}))
    (tmp_path / "raw" / "0e8b1b1e-1111-4222-8333-444455556666.json").write_text(json.dumps({"source": "generated"}))
    assert r.generated_ids(tmp_path, tmp_path / "none") == ["0e8b1b1e-1111-4222-8333-444455556666"]


def test_raw_files_that_are_not_json_objects_are_skipped_not_fatal(tmp_path):
    (tmp_path / "raw").mkdir()
    for name, body in (("0e8b1b1e-1111-4222-8333-444455556661", "[]"), ("0e8b1b1e-1111-4222-8333-444455556662", "null"),
                       ("0e8b1b1e-1111-4222-8333-444455556663", "{broken"), ("0e8b1b1e-1111-4222-8333-444455556664", '"text"')):
        (tmp_path / "raw" / f"{name}.json").write_text(body)
    assert r.generated_ids(tmp_path, tmp_path / "none") == []


def test_a_generated_passages_human_variant_files_are_included_too(tmp_path):
    make(tmp_path)
    gen = "0e8b1b1e-0000-4000-8000-000000000002"
    human = "0e8b1b1e-0000-4000-8000-0000000000aa"
    (tmp_path / f"{gen}.timing.json").write_text(json.dumps({"pairId": human}))
    (tmp_path / f"{human}.mp3").write_text("h")
    (tmp_path / f"{human}.timing.json").write_text(json.dumps({"pairId": gen}))
    names = sorted(p.name for p in r.plan(tmp_path)["files"])
    assert f"{human}.mp3" in names and f"{human}.timing.json" in names


def test_a_corrupt_state_file_stops_with_a_clear_message_and_changes_nothing(tmp_path):
    import pytest

    (tmp_path / "state.json").write_text("{broken")
    with pytest.raises(SystemExit, match="state.json"):
        r.plan(tmp_path)
    assert (tmp_path / "state.json").read_text() == "{broken"


def test_apply_leaves_no_temp_file_behind(tmp_path):
    make(tmp_path)
    r.apply(tmp_path, r.plan(tmp_path))
    assert not list(tmp_path.glob("*.tmp"))


def test_a_translation_of_a_deleted_teacher_passage_is_deleted_too_but_a_sample_translation_is_kept(tmp_path):
    make(tmp_path)
    gen = "0e8b1b1e-0000-4000-8000-000000000002"      # teacher-generated
    sample = "0e8b1b1e-0000-4000-8000-000000000001"   # built-in sample
    t_gen, t_sample = "0e8b1b1e-0000-5000-8000-0000000000a1", "0e8b1b1e-0000-5000-8000-0000000000a2"
    for tid, source in ((t_gen, gen), (t_sample, sample)):
        (tmp_path / f"{tid}.timing.json").write_text(json.dumps({"id": tid, "translationOf": {"id": source, "lang": "en", "sentenceMap": [0]}}))
        (tmp_path / f"{tid}.mp3").write_text("a")
        (tmp_path / f"{tid}.cards.json").write_text("{}")
        (tmp_path / f"{tid}.place-x-12345678.jpg").write_text("p")
        (tmp_path / f"{tid}.word-y-12345678.png").write_text("w")
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / f"{sample}.json").write_text("{}")
    names = {p.name for p in r.plan(tmp_path, samples)["files"]}
    assert f"{t_gen}.mp3" in names and f"{t_gen}.timing.json" in names and f"{t_gen}.place-x-12345678.jpg" in names and f"{t_gen}.word-y-12345678.png" in names
    assert not any(n.startswith(t_sample) for n in names)
    r.apply(tmp_path, r.plan(tmp_path, samples))
    assert not (tmp_path / f"{t_gen}.mp3").exists() and (tmp_path / f"{t_sample}.mp3").exists()


def test_a_translation_pointing_at_a_missing_source_is_also_removed(tmp_path):
    make(tmp_path)
    orphan = "0e8b1b1e-0000-5000-8000-0000000000b1"
    (tmp_path / f"{orphan}.timing.json").write_text(json.dumps({"id": orphan, "translationOf": {"id": "0e8b1b1e-9999-4000-8000-000000000000"}}))
    (tmp_path / f"{orphan}.mp3").write_text("a")
    assert f"{orphan}.mp3" in {p.name for p in r.plan(tmp_path, tmp_path / "none")["files"]}
