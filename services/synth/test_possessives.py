"""Choosing his, her or their for Spanish su/sus from the sentences before it."""
import pytest

import possessives as ps
import translate as tr


def scorer_for(preferred, strength=2.0):
    """A scorer that supports `preferred` and treats the other two as equally unlikely."""
    return lambda context, before: {o: (strength if o == preferred else 0.0) for o in ps.OPTIONS}


def test_possessive_slots_skip_the_object_pronoun_her_and_a_pronoun_with_nothing_after_it():
    assert [w for _, _, w in ps.possessive_slots("The park is close to his house.")] == ["his"]
    assert ps.possessive_slots("The teacher gave her the book.") == []
    assert [w for _, _, w in ps.possessive_slots("She read her favorite book.")] == ["her"]
    assert ps.possessive_slots("The book is his.") == []
    assert [w for _, _, w in ps.possessive_slots("Their dog and her cat sleep.")] == ["Their", "her"]


def test_a_wrong_pronoun_is_replaced_when_the_context_clearly_prefers_another():
    out = ps.resolve_possessives(["Ana y Pablo van al parque.", "El parque está cerca de su casa."], ["Ana and Pablo go to the park.", "The park is close to his house."], scorer_for("their"))
    assert out[1] == "The park is close to their house."


def test_the_translators_choice_is_kept_unless_the_evidence_is_clear():
    sources = ["Ana lee.", "Su libro es azul."]
    outputs = ["Ana reads.", "Her book is blue."]
    weak = lambda c, b: {"his": 0.0, "her": 0.0, "their": 0.5}  # their wins, but by less than the margin  # noqa: E731
    assert ps.resolve_possessives(sources, outputs, weak)[1] == "Her book is blue."
    strong = lambda c, b: {"his": 0.0, "her": 0.0, "their": 3.0}  # noqa: E731
    assert ps.resolve_possessives(sources, outputs, strong)[1] == "Their book is blue."


def test_capitalisation_of_a_sentence_start_is_kept():
    out = ps.resolve_possessives(["Ana y Pablo juegan.", "Su perro duerme."], ["Ana and Pablo play.", "His dog sleeps."], scorer_for("their"))
    assert out[1] == "Their dog sleeps."


def test_sentences_without_su_or_with_a_different_number_of_slots_are_left_alone():
    sources = ["Ana y Pablo juegan.", "Mi perro duerme.", "Su casa y su jardín son bonitos."]
    outputs = ["Ana and Pablo play.", "My dog sleeps.", "His house is nice."]  # two su but one slot: do not guess
    assert ps.resolve_possessives(sources, outputs, scorer_for("their")) == outputs


def test_the_first_sentence_has_nothing_before_it_so_it_is_not_changed():
    assert ps.resolve_possessives(["Su casa es grande."], ["His house is big."], scorer_for("their")) == ["His house is big."]


def test_two_pronouns_in_one_sentence_are_each_decided():
    out = ps.resolve_possessives(["Ana y Pablo juegan.", "Su madre y su padre miran."], ["Ana and Pablo play.", "His mother and her father watch."], scorer_for("their"))
    assert out[1] == "Their mother and their father watch."


def test_a_scorer_that_fails_changes_nothing_and_no_scorer_is_a_no_op():
    def broken(context, before):
        raise RuntimeError("boom")

    sources, outputs = ["Ana y Pablo juegan.", "Su perro duerme."], ["Ana and Pablo play.", "His dog sleeps."]
    assert ps.resolve_possessives(sources, outputs, broken) == outputs
    assert ps.resolve_possessives(sources, outputs, None) == outputs


def test_the_scorer_is_off_when_switched_off_or_the_model_folder_is_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("POSSESSIVE_FIX", "off")
    assert ps.load_scorer() is None
    monkeypatch.delenv("POSSESSIVE_FIX")
    monkeypatch.setenv("POSSESSIVE_LM_DIR", str(tmp_path / "missing"))
    assert ps.load_scorer() is None
    monkeypatch.setenv("POSSESSIVE_LM_DIR", str(tmp_path))
    assert isinstance(ps.load_scorer(), ps.PronounScorer)


def test_translate_passage_uses_the_scorer_for_the_translation_of_each_sentence_and_keeps_the_sentence_map():
    class Fixed:
        def __call__(self, texts):
            return [{"Ana y Pablo van al parque.": "Ana and Pablo go to the park.", "El parque está cerca de su casa.": "The park is close to his house."}.get(t, t) for t in texts]

    html = "<p>Ana y Pablo van al parque. El parque está cerca de su casa.</p>"
    out = tr.translate_passage({"title": "", "content": html}, Fixed(), names_fn=lambda t: [], pronoun_scorer=scorer_for("their"))
    assert "close to their house" in out.content_html and out.sentence_map == [[0], [1]]
    plain = tr.translate_passage({"title": "", "content": html}, Fixed(), names_fn=lambda t: [])
    assert "close to his house" in plain.content_html


def test_the_real_model_chooses_their_for_a_group_and_her_for_a_girl():
    pytest.importorskip("transformers")
    scorer = ps.PronounScorer()
    try:
        scorer("Ana and Pablo go to the park.", "The park is close to")
    except Exception as err:  # noqa: BLE001 (model not downloaded / offline)
        pytest.skip(f"model not available: {err}")
    group = ps.resolve_possessives(["Ana y su hermano Pablo van al parque con su abuela.", "El parque está cerca de su casa."],
                                   ["On Saturdays, Ana and her brother Pablo go to the park with their grandmother.", "The park is close to his house and has tall trees."], scorer)
    assert "their house" in group[1]
    girl = ps.resolve_possessives(["Marta abrió la puerta.", "Ella sonrió a los visitantes.", "Su madre esperaba dentro."], ["Marta opened the door.", "She smiled at the visitors.", "His mother was waiting inside."], scorer)
    assert girl[2].startswith("Her mother")
