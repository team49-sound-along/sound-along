"""Generate audio + word timing for one passage, locally.

CLI:  python run_local.py <job-input.json> <data_dir>
Prints JSON lines on stdout: {"step": ...} progress lines, then one {"result": {...}} line.

The input file is the job input described in docs/API.md ("Job input file"): uuid, title, content (HTML) and
optionally settings (voice, speed, mp3Kbps), pronunciations, recording {path}, humanPassageId, qualityCheck and
vocab (ReadWorks shape). Everything a teacher can change arrives through this file, not through code.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from engine import SAMPLE_RATE
from engines import create_engine
from fingerprint import fingerprint
from flow import Variant, run_flow, soundalong_block
from mp3 import encode_mp3, resolve_kbps
from stitch import Chunk, Stitched, link_translation, retarget_ids, stitch


def _emit_step(step: str) -> None:
    sys.stdout.write(json.dumps({"step": step}) + "\n")
    sys.stdout.flush()


def _write_variant(variant: Variant, data_dir: Path, kbps: int, keep_pcm: bool = False) -> None:
    (data_dir / f"{variant.id}.mp3").write_bytes(encode_mp3(variant.audio, SAMPLE_RATE, kbps))
    if keep_pcm:  # a chunk of a long document: the exact samples, so joining chunks never decodes and re-encodes an MP3
        np.save(data_dir / f"{variant.id}.pcm.npy", (np.clip(variant.audio, -1.0, 1.0) * 32767).astype(np.int16))
    timing_file = data_dir / f"{variant.id}.timing.json"
    timing = variant.timing
    if "pairId" not in timing and timing_file.exists():
        # regenerating the AI voice of a passage that already has a human pair must not break that link
        existing = json.loads(timing_file.read_text()).get("pairId")
        if existing:
            timing = {**timing, "pairId": existing}
    timing_file.write_text(json.dumps(timing, ensure_ascii=False))


def _unchanged(passage: dict[str, Any], data_dir: Path, fp: str) -> dict[str, Any] | None:
    """The previous output when its fingerprint matches (same text, voice, settings, relevant fixes, recording)."""
    timing_file = data_dir / f"{passage['uuid']}.timing.json"
    if passage.get("force") or not timing_file.exists() or not (data_dir / f"{passage['uuid']}.mp3").exists():
        return None
    previous = json.loads(timing_file.read_text())
    return previous if previous.get("generatedWith", {}).get("hash") == fp else None


def publish_cards(passage: dict[str, Any], data_dir: Path, enrich_fn=None) -> bool:
    """Place cards and pictures for a teacher-generated passage, written next to the audio. Best effort: never raises, so the audio
    that is already published is never lost to a slow or blocked network."""
    try:
        from enrich_places import enrich_places, ner_places, write_enriched
        from word_cards import word_cards

        enriched = enrich_fn(passage) if enrich_fn else enrich_places({**passage, "source": passage.get("source") or "generated"}, ner=ner_places, words=word_cards)
        return bool(enriched and write_enriched(data_dir, passage["uuid"], enriched))
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"place cards skipped: {err}\n")
        return False


def _already_published(variant: Variant, data_dir: Path) -> bool:
    """True when this passage is already in the Library (a regeneration): it must stay listed while it is rebuilt."""
    try:
        return not json.loads((data_dir / f"{variant.id}.timing.json").read_text()).get("held")
    except (OSError, ValueError):
        return False


def _held_if_translating(passage: dict[str, Any], variant: Variant, data_dir: Path | None = None) -> Variant:
    """A NEW passage that is about to get a translation stays out of the Library (`held`) until the translation is in place, so the original
    and its translation appear together. `main` releases it when the translation is done or has failed. A passage that is already
    published (regenerate) is never held: it must not disappear while it is rebuilt."""
    from translate_flow import should_translate

    if not should_translate(passage) or (data_dir is not None and _already_published(variant, data_dir)):
        return variant
    return dataclasses.replace(variant, timing={**variant.timing, "held": True})


def run(passage: dict[str, Any], data_dir: Path, on_step=_emit_step) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = passage.get("settings") or {}
    recording = (passage.get("recording") or {}).get("path")
    previous = _unchanged(passage, data_dir, fingerprint(passage, recording))
    if previous is not None:  # nothing that affects the audio changed: no generation, no cost
        return {"id": passage["uuid"], "humanPassageId": previous.get("pairId") if recording else None,
                "title": passage.get("title"), "skipped": True, **previous["metrics"]}
    engine = create_engine(settings=settings, respellings=passage.get("pronunciations"), language=passage.get("language") or "en")
    result = run_flow(passage, engine, on_step, recording_path=recording)

    on_step("publish")
    kbps = resolve_kbps(settings.get("mp3Kbps"))
    ai, human = _held_if_translating(passage, result.ai, data_dir), (_held_if_translating(passage, result.human, data_dir) if result.human else None)
    keep_pcm = bool(passage.get("keepPcm"))
    _write_variant(ai, data_dir, kbps, keep_pcm)
    if human:
        _write_variant(human, data_dir, kbps)
    (data_dir / f"{result.ai.id}.soundalong.json").write_text(json.dumps(result.soundalong, ensure_ascii=False))
    publish_cards(passage, data_dir)
    return {
        "id": result.ai.id,
        "humanPassageId": result.human.id if result.human else None,
        "title": passage.get("title"),
        **result.ai.timing["metrics"],
    }


def translate_after_publish(passage: dict[str, Any], data_dir: Path, summary: dict[str, Any]) -> Optional[str]:
    """The other-language version of a teacher's passage, made AFTER the original is published (so the teacher is never kept waiting).
    Best effort: any failure leaves the original untouched. Returns the translated passage id or None."""
    try:
        from translate_flow import other_language, publish_translation, should_translate

        if not should_translate(passage):
            return None
        ids = [summary["id"], *([summary["humanPassageId"]] if summary.get("humanPassageId") else [])]
        return publish_translation({**passage, "uuid": summary["id"]}, data_dir, other_language(passage.get("language")), source_ids=ids, safe=True)
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"translation skipped: {err}\n")
        return None


CHUNK_NAMESPACE = uuid.UUID("6b2f7c1e-3d54-4a0b-8e77-1f2c9a5d0b64")
PICTURE_PREFIXES = ("word-", "place-", "figure-")


def chunk_id(document_id: str, k: int) -> str:
    """The internal id of chunk `k` of a long document. Chunks live in a work folder and are never listed."""
    return str(uuid.uuid5(CHUNK_NAMESPACE, f"{document_id}:{k}"))


def _emit_chunk(done: int, total: int) -> None:
    sys.stdout.write(json.dumps({"chunk": {"done": done, "total": total}}) + "\n")
    sys.stdout.flush()


def _load_chunk(work: Path, passage_id: str) -> Chunk:
    timing = json.loads((work / f"{passage_id}.timing.json").read_text())
    timing.pop("held", None)
    audio = np.load(work / f"{passage_id}.pcm.npy").astype(np.float32) / 32768.0
    cards_file = work / f"{passage_id}.cards.json"
    return Chunk(timing, audio, json.loads(cards_file.read_text()) if cards_file.exists() else None)


def _publish_stitched(data_dir: Path, work: Path, stitched: Stitched, timing: dict[str, Any], chunk_ids: list[str], kbps: int) -> None:
    """Write one stitched passage: audio, sound-along block, cards with their pictures, and the timing document last (it is what lists the passage)."""
    pid = timing["id"]
    (data_dir / f"{pid}.mp3").write_bytes(encode_mp3(stitched.audio, SAMPLE_RATE, kbps))
    (data_dir / f"{pid}.soundalong.json").write_text(json.dumps(soundalong_block(timing), ensure_ascii=False))
    if stitched.cards:
        (data_dir / f"{pid}.cards.json").write_text(json.dumps(retarget_ids(stitched.cards, chunk_ids, pid), ensure_ascii=False))
        for source in work.iterdir():
            for old in chunk_ids:
                rest = source.name[len(old) + 1:] if source.name.startswith(f"{old}.") else ""
                if rest.startswith(PICTURE_PREFIXES):
                    shutil.copyfile(source, data_dir / f"{pid}.{rest}")
    (data_dir / f"{pid}.timing.json").write_text(json.dumps(timing, ensure_ascii=False))


def run_document(passage: dict[str, Any], data_dir: Path, on_chunk: Callable[[int, int], None] = _emit_chunk, on_step: Callable[[str], None] = _emit_step,
                 run_fn: Callable[..., dict[str, Any]] = run, translate_fn: Callable[..., Optional[str]] = translate_after_publish) -> dict[str, Any]:
    """A long upload as ONE passage. `passage["chunks"]` are the HTML pieces (each fits one generator run). Every chunk is narrated and translated in a work
    folder, then stitch.py joins them into a single passage per language, published together. Nothing in the Library ever shows a chunk."""
    from translate_flow import other_language, release, should_translate, translated_id

    data_dir.mkdir(parents=True, exist_ok=True)
    final_id, chunks_html = passage["uuid"], passage["chunks"]
    work = data_dir / "work" / final_id
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    ids = [chunk_id(final_id, k) for k in range(len(chunks_html))]
    translating = should_translate(passage)
    try:
        for k, (cid, html) in enumerate(zip(ids, chunks_html)):
            job = {**passage, "uuid": cid, "content": html, "chunks": None, "series": None, "keepPcm": True, "force": True}
            summary = run_fn(job, work, on_step=lambda step: None)
            if translating:
                translate_fn(job, work, summary)
            on_chunk(k + 1, len(chunks_html))
        on_step("publish")
        kbps = resolve_kbps((passage.get("settings") or {}).get("mp3Kbps"))
        source_lang = passage.get("language") or "en"
        lang = other_language(source_lang)
        en_chunks = [_load_chunk(work, cid) for cid in ids]
        en = stitch(en_chunks, final_id, passage.get("title") or "Untitled passage", fingerprint=fingerprint({**passage, "chunks": None}))
        target_ids = [translated_id(cid, lang) for cid in ids]
        complete = translating and all((work / f"{t}.timing.json").exists() and (work / f"{t}.pcm.npy").exists() for t in target_ids)
        if not complete:  # no translation, or one chunk of it failed: the passage is published in its own language only, never half translated
            _publish_stitched(data_dir, work, en, en.timing, ids, kbps)
            return {"id": final_id, "humanPassageId": None, "title": passage.get("title"), **en.timing["metrics"]}
        es_chunks = [_load_chunk(work, t) for t in target_ids]
        tid = translated_id(final_id, lang)
        es = stitch(es_chunks, tid, es_chunks[0].timing.get("title") or passage.get("title") or "")
        en_timing, es_timing = link_translation(en, es, en_chunks, es_chunks, lang, source_lang, final_id, tid)
        _publish_stitched(data_dir, work, es, {**es_timing, "held": True}, target_ids, kbps)
        _publish_stitched(data_dir, work, en, {**en_timing, "held": True}, ids, kbps)
        release(data_dir, [tid, final_id])  # both languages appear together
        return {"id": final_id, "humanPassageId": None, "title": passage.get("title"), **en.timing["metrics"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(passage_path: str, data_dir: str) -> int:
    passage = json.loads(Path(passage_path).read_text())
    if passage.get("chunks"):
        sys.stdout.write(json.dumps({"result": run_document(passage, Path(data_dir))}) + "\n")
        sys.stdout.flush()
        return 0
    summary = run(passage, Path(data_dir))
    # The job is reported done only after the translation is in place (or has failed), and the passage is released then, never before.
    from translate_flow import release

    _emit_step("translate")
    try:
        translate_after_publish(passage, Path(data_dir), summary)
    finally:
        release(Path(data_dir), [summary["id"], *([summary["humanPassageId"]] if summary.get("humanPassageId") else [])])
    sys.stdout.write(json.dumps({"result": summary}) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
