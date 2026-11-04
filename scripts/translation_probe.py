"""Print a fixed list of tricky sentences through the translator, so any change to it can be judged against the same list.

  .venv/bin/python scripts/translation_probe.py            # the model the app uses
  .venv/bin/python scripts/translation_probe.py --names    # also run each sentence through the passage path (place names protected)

The sentences are our own (no ReadWorks text). Each one is a mistake we saw in a real translation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "services" / "synth"), str(ROOT / "services" / "parse")]

ES_EN = [
    "Los sábados, Ana y su hermano Pablo van al parque con su abuela.",
    "El parque está cerca de su casa y tiene árboles muy altos.",
    "Ana prefiere sentarse debajo de un árbol para leer su libro favorito.",
    "Los niños comen y hablan de lo que van a hacer esta tarde.",
    "Pedro y Lucía llegaron tarde porque su autobús se rompió.",
    "La maestra le dio a Sara su cuaderno nuevo.",
]
EN_ES = [
    "Tea was first brought to Britain from China.",
    "In Britain, many people drink tea every afternoon.",
    "This was a great deal for the company.",
    "They sneaked in tea that was cheaper.",
    "Maria told her brother that she would pick him up at school.",
    "The boys left their bikes near the lake and ran home.",
]


def run(pair: tuple[str, str], sentences: list[str], names: bool) -> None:
    import translate as tr

    model = tr.load_model(*pair)
    print(f"\n=== {pair[0]} -> {pair[1]} ===")
    for src, out in zip(sentences, model(sentences)):
        print(f"  {src}\n    -> {out}")
    if names:
        t = tr.translate_passage({"title": "", "content": "<p>" + " ".join(sentences) + "</p>"}, model, names_fn=lambda text: ["Britain", "China", "Ana", "Pablo", "Pedro", "Lucía", "Sara", "Maria"])
        print("  [passage path]", t.content_html)


if __name__ == "__main__":
    names = "--names" in sys.argv
    run(("es", "en"), ES_EN, names)
    run(("en", "es"), EN_ES, names)
