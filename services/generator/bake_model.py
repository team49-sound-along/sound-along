"""Build-time only: download the pinned models into HF_HOME and point refs/main at them.

 * Kokoro-82M weights plus every US/UK English voice (teachers choose the voice in Settings, so all must be present).
 * faster-whisper small.en (MIT) for aligning uploaded recordings and the pronunciation check, and the multilingual
   small model for Spanish.

The libraries load repos with the default revision ("main"), so offline lookups need refs/main to exist;
snapshot_download with a commit hash does not write it.
"""
from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE

MODELS = (
    (
        "hexgrad/Kokoro-82M",
        "f3ff3571791e39611d31c381e3a41a3af07b4987",
        ["config.json", "kokoro-v1_0.pth", "voices/af_*.pt", "voices/am_*.pt", "voices/bf_*.pt", "voices/bm_*.pt", "voices/ef_*.pt", "voices/em_*.pt"],
    ),
    (
        "Systran/faster-whisper-small.en",
        "d1d751a5f8271d482d14ca55d9e2deeebbae577f",
        ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"],
    ),
    (  # multilingual: Spanish word timing and checks
        "Systran/faster-whisper-small",
        "536b0662742c02347bc0e980a01041f333bce120",
        ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"],
    ),
)


# Phonon (Apache-2.0): the English model and only the two offered voices, as plain folders the `ptts` runtime loads from disk
# (PHONON_MODEL_DIR / PHONON_VOICES_DIR), so nothing is downloaded at run time. Revisions match services/synth/phonon_engine.py.
PHONON_DIR = Path("/opt/phonon")
PHONON = (
    (  # f32 weights only: the quantized .gguf copies (about 110 MB) are not used
        "gradium/phonon-31m-en",
        "8c64b55ec301728e2d1695bfea87a08a267d0c2d",
        "model",
        ["config.json", "model.safetensors", "default-voice.safetensors", "tokenizer.json", "tokenizer.model"],
    ),
    (
        "gradium/phonon-voices",
        "da6c9ec0d47be8df5c87c730a3aa97187f3229c3",
        "voices",
        ["voices.jsonl", "voices/bXwrkHhURL1VFJdG.safetensors", "voices/vjFyp2BcCyTlUmYb.safetensors"],  # Hadley, Everly
    ),
)


# Opus-MT English<->Spanish (Apache-2.0), pinned by full commit hash, loaded from disk (TRANSLATE_MODELS_DIR) with local_files_only.
TRANSLATE_DIR = Path("/opt/translate")
TRANSLATE = (
    ("Helsinki-NLP/opus-mt-en-es", "5bc4493d463cf000c1f0b50f8d56886a392ed4ab", "en-es"),
    ("Helsinki-NLP/opus-mt-es-en", "c96e2c5399ebfae4fc43d9669556b9afa74bb69d", "es-en"),
    ("Helsinki-NLP/opus-mt-tc-big-en-es", "8f4d4924189681076e9c642b2fd85278d793fd4d", "en-es-big"),  # CC-BY-4.0: English passages up to 900 words (see translate.BIG)
    ("Helsinki-NLP/opus-mt-tc-bible-big-roa-en", "4d4757865ab116b39daa3b4ca3cfe1e7daf43cbe", "es-en-big"),  # Apache-2.0: Spanish passages up to 900 words
)
TRANSLATE_FILES = ["config.json", "generation_config.json", "pytorch_model.bin", "source.spm", "special_tokens_map.json", "target.spm", "tokenizer_config.json", "vocab.json"]


HALF_PRECISION_ON_DISK = ("es-en-big",)  # stored as float16 (467 MB instead of 933 MB); loaded back as float32. Checked: identical translations on 38 sentences.


def bake_translation() -> None:
    for repo, revision, folder in TRANSLATE:
        target = TRANSLATE_DIR / folder
        snapshot_download(repo, revision=revision, local_dir=str(target), allow_patterns=TRANSLATE_FILES)
        if folder in HALF_PRECISION_ON_DISK:
            import torch
            from transformers import MarianMTModel

            MarianMTModel.from_pretrained(str(target), dtype=torch.float16).save_pretrained(str(target), safe_serialization=True)
            (target / "pytorch_model.bin").unlink()
            for f in target.iterdir():  # Lambda runs as a different, non-root user: every file must be world-readable
                if f.is_file():
                    f.chmod(0o644)


def bake_phonon() -> None:
    for repo, revision, folder, files in PHONON:
        snapshot_download(repo, revision=revision, local_dir=str(PHONON_DIR / folder), allow_patterns=files)


def main() -> None:
    for repo, revision, files in MODELS:
        snapshot_download(repo, revision=revision, allow_patterns=files)
        refs = Path(HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}" / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "main").write_text(revision)
    bake_phonon()
    bake_translation()


if __name__ == "__main__":
    main()
