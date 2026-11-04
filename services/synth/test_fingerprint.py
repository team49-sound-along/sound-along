from fingerprint import fingerprint

BASE = {"uuid": "p", "title": "T", "content": "<p>The gaieties were fun.</p>", "language": "en",
        "settings": {"voice": "af_heart", "speed": 0.95, "mp3Kbps": 48}, "pronunciations": {"gaieties": "gayetees"}}


def test_same_input_gives_the_same_fingerprint():
    assert fingerprint(BASE) == fingerprint({**BASE})


def test_changing_the_text_voice_speed_bitrate_or_language_changes_it():
    base = fingerprint(BASE)
    assert fingerprint({**BASE, "content": "<p>Other text.</p>"}) != base
    assert fingerprint({**BASE, "settings": {**BASE["settings"], "voice": "af_bella"}}) != base
    assert fingerprint({**BASE, "settings": {**BASE["settings"], "speed": 1.0}}) != base
    assert fingerprint({**BASE, "settings": {**BASE["settings"], "mp3Kbps": 32}}) != base
    assert fingerprint({**BASE, "language": "es"}) != base


def test_only_pronunciation_fixes_that_appear_in_the_passage_matter():
    base = fingerprint(BASE)
    assert fingerprint({**BASE, "pronunciations": {**BASE["pronunciations"], "zebra": "zee-bruh"}}) == base  # not in the text
    assert fingerprint({**BASE, "pronunciations": {"gaieties": "gay-eh-teez"}}) != base  # in the text, different fix
    assert fingerprint({**BASE, "pronunciations": {}}) != base  # fix removed


def test_voice_choice_is_per_language_so_an_unused_voice_setting_never_triggers_a_rebuild():
    en = fingerprint(BASE)
    assert fingerprint({**BASE, "settings": {**BASE["settings"], "voiceEs": "em_alex"}}) == en  # Spanish voice irrelevant to English
    es = {**BASE, "language": "es", "content": "<p>Hola amigos.</p>", "pronunciations": {}}
    assert fingerprint({**es, "settings": {**es["settings"], "voice": "bf_emma"}}) == fingerprint(es)


def test_a_recording_changes_it_by_content_not_by_path(tmp_path):
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    a.write_bytes(b"one")
    b.write_bytes(b"one")
    with_a = fingerprint({**BASE, "humanPassageId": "h"}, str(a))
    assert with_a == fingerprint({**BASE, "humanPassageId": "h"}, str(b))  # same bytes, different path
    b.write_bytes(b"two")
    assert with_a != fingerprint({**BASE, "humanPassageId": "h"}, str(b))
    assert with_a != fingerprint(BASE)


def test_force_and_title_do_not_change_it():
    base = fingerprint(BASE)
    assert fingerprint({**BASE, "force": True, "title": "A new title"}) == base


def test_choosing_another_engine_changes_it_but_an_unset_engine_keeps_old_hashes():
    base = fingerprint(BASE)
    assert fingerprint({**BASE, "settings": {**BASE["settings"], "ttsEngine": None}}) == base  # passages made before the setting existed
    kokoro = fingerprint({**BASE, "settings": {**BASE["settings"], "ttsEngine": "kokoro"}})
    polly = fingerprint({**BASE, "settings": {**BASE["settings"], "ttsEngine": "polly"}})
    assert kokoro != polly
