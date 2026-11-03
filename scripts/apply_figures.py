"""Show ReadWorks' own passage pictures between paragraphs.

  .venv/bin/python scripts/apply_figures.py          # after build_samples.py (it runs build_translations first)

Downloads each sample passage's figures from ReadWorks' own image host into data/ (never into the repository: they are ReadWorks' images) and
adds a `figures` list to that passage's cards document. Translated copies get the same pictures under their own id, with the caption and alt
text machine-translated when the translation model is installed. Safe to re-run. Pictures that cannot be fetched are skipped.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "services" / "synth"), str(ROOT / "services" / "parse")]
from figures import extract_figures, fetch_figures  # noqa: E402
from place_media import target_name  # noqa: E402

DATA, SAMPLES = ROOT / "data", ROOT / "samples"


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SoundAlong-build/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (host allow-listed by extract_figures)
        return r.read(3_000_001)


def with_figures(doc: dict, entries: list[dict]) -> dict:
    return {**doc, "figures": entries}


def _translate(texts: list[str], model, names: list[str]) -> list[str]:
    """Translate with place names protected, exactly as the passage body does (so "Piedmont Park" stays "Piedmont Park")."""
    import translate as tr

    masked = [tr.mask(t, names) for t in texts]
    out = model([m for m, _ in masked])
    return [tr.unmask(o, table) for o, (_, table) in zip(out, masked)]


def translated_entries(entries: list[dict], pid: str, tid: str, lang: str, model, names: list[str] | None = None) -> tuple[list[dict], dict[str, bytes]]:
    """The same pictures under the translated passage's id, text translated when a model is given."""
    out, files = [], {}
    for e in entries:
        old = e["imageUrl"].removeprefix("/data/")
        data = (DATA / old).read_bytes()
        name = target_name(tid, old.split(".figure-")[1].split("-")[0], data, kind="figure")
        text = [e["imageAlt"], e.get("caption", "")]
        alt, cap = _translate(text, model, names) if model else text
        out.append({**e, "imageUrl": f"/data/{name}", "imageAlt": alt or e["imageAlt"], **({"caption": cap} if e.get("caption") else {})})
        files[name] = data
    return out, files


def main() -> int:
    done = 0
    translations: dict[str, list[tuple[str, str]]] = {}
    for timing in DATA.glob("*.timing.json"):
        link = (json.loads(timing.read_text(encoding="utf-8")).get("translationOf") or {})
        if link.get("id"):
            translations.setdefault(link["id"], []).append((timing.name.removesuffix(".timing.json"), link.get("lang", "es")))
    models: dict[str, object] = {}
    for sample in sorted(SAMPLES.glob("*.json")):
        passage = json.loads(sample.read_text(encoding="utf-8"))
        figs = extract_figures(passage.get("content", ""))
        if not figs:
            continue
        pid = sample.stem
        entries, images = fetch_figures(pid, figs, http_get)
        for name, data in images.items():
            (DATA / name).write_bytes(data)
        cards = DATA / f"{pid}.cards.json"
        if not entries or not cards.exists():
            print(f"{pid[:8]}: {len(figs)} figure(s) found, {len(entries)} fetched, cards file {'present' if cards.exists() else 'MISSING'}: skipped")
            continue
        cards.write_text(json.dumps(with_figures(json.loads(cards.read_text(encoding="utf-8")), entries), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{pid[:8]}: {len(entries)} figure(s)")
        done += len(entries)
        for tid, lang in translations.get(pid, []):
            target = "es" if passage.get("language", "en") == "en" else "en"
            if target not in models:
                try:
                    import translate as tr

                    m = tr.load_model(passage.get("language", "en"), target)
                    models[target] = lambda xs, m=m: m(xs)
                except Exception as err:  # noqa: BLE001
                    print(f"  translation model not available ({err}); captions stay in the original language")
                    models[target] = None
            doc = json.loads(cards.read_text(encoding="utf-8"))
            names = [n for c in doc.get("places", {}).values() for n in (c.get("name"),) if n] + list(doc.get("places", {}))
            t_entries, files = translated_entries(entries, pid, tid, target, models[target], names)
            for name, data in files.items():
                (DATA / name).write_bytes(data)
            tcards = DATA / f"{tid}.cards.json"
            if tcards.exists():
                tcards.write_text(json.dumps(with_figures(json.loads(tcards.read_text(encoding="utf-8")), t_entries), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"  {tid[:8]} ({target}): {len(t_entries)} figure(s)")
    print(f"{done} figure(s) added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
