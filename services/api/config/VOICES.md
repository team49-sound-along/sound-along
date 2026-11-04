# Which voices are offered, and why

Only voices that Kokoro's authors grade **B- or better** are offered for English. Their published grade estimates the quality and
quantity of each voice's training data (<https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md>): af_heart A, af_bella A-,
af_nicole B-, bf_emma B-. Every other English voice is graded C+ or lower (for example am_adam F+), so it is not offered.
No male English voice reaches the bar (the best are C+).

The three Spanish voices have no published grade at all, and Kokoro's Spanish uses a basic pronunciation step, so Spanish quality is
**unverified**. Have a Spanish speaker listen before relying on it.

We could not rank voices by a naturalness predictor: UTMOS scored a C-graded voice above the A-graded one, so it measures audio
cleanliness, not how human a voice sounds. Run `scripts/voice_bakeoff.py` for the measurements, and use the blind listening test
for the real decision. Adding a voice to `voices.json` is all it takes to offer it.

## Next candidate (not offered yet)
Phonon 31M-en (gradium/phonon-31m-en, Apache-2.0, `ptts` package) is the licence-safe challenger. It scored well on the same
automatic checks, but nobody has listened to it, and adding it grows the generator image. Offer it only after the blind
audition (8 clips, see the team notes) puts it above the Kokoro voices. Its Spanish models are CC BY-NC 4.0 and gated, so they
cannot be used here.

## Listening results (blind, 8 clips, 2 reviewers, 2026-11-03)
Both reviewers sent the same clips back in the same order, so the result is consistent but small (n=2, one 53-word passage).
- **Robotic / shrill / creepy, so removed:** af_bella, bf_emma, af_nicole (reviewer 1 called Nicole "a bit creepy", reviewer 2 "the worst").
- **Kept:** af_heart ranked first by both reviewers.
- **Also rated well:** Phonon Everly and Hadley (top 3 for both). Phonon Spencer was called human but with a strong British accent.
- **ReadWorks' human clip** was rated "not good" by one reviewer (more treble, male voice, recording noise), so it is not a gold standard.
- Phonon is English only here (Spanish models are non-commercial).

## Phonon is now offered (2026-11-03)
Hadley and Everly (`phonon_hadley`, `phonon_everly`) are selectable English voices, run by `services/synth/phonon_engine.py`.
- Chosen by voice id: the generator picks the engine from the voice, so selecting a voice in Settings is enough.
- No speed control in the model: the Settings speed does not apply to them (students still change playback speed in the reader).
- No word times from the model: Whisper supplies them (as for Spanish), so a word can occasionally be unaligned. The Insights
  quality numbers and the per-passage review show this honestly. Number words ("twenty", "one hundred") are the usual unmatched ones.
- Pronunciation fixes: plain respellings work, `/phoneme/` entries are Kokoro-only and are skipped.
- Image: the model (f32, about 99 MB) and the two voice files are baked into the generator image at pinned revisions and loaded
  from `/opt/phonon`, so nothing is downloaded at run time. The default stays `af_heart`.
- Labels come from the voice catalog's own metadata (gender, age, description).

## The five English and three Spanish voices (2026-11-04)
Only the most human-sounding voices are offered, each with a "Hear it" sample in Settings (`web/public/voice-samples/<id>.mp3`, made by
`scripts/build_voice_samples.py`; run it again after changing `voices.json`).
- **English (5):** Heart (Kokoro, grade A), Phonon Hadley and Everly (top 3 with Heart for both blind reviewers), plus Phonon Bryony (UK female,
  "full, rich, relaxed, close to the mic") and Trevor (US male, "resonant mid-low core") as narration-style additions. Bryony and Trevor have
  **not been rated by anyone yet**: listen to them in Settings before relying on them.
- **Removed:** the other Kokoro English voices. Kokoro's grades do not predict how human a voice sounds (Bella A- and Nicole B- were called robotic,
  shrill or creepy), and everything else is C+ or lower.
- **Spanish (2):** Kokoro Dora and Alex. Santa was removed after a listening round (rated no). In the same round MeloTTS Spanish and Qwen3-TTS were rated yes and VoxCPM2 no; none of them is in the app yet 
  - **MeloTTS Spanish:** code and model weights are both MIT (model card checked 2026-11-04). It cannot go into the generator image as it is: it pins `transformers==4.27.4` and
    `librosa==0.9.1`, while the image runs `transformers==5.22.1` and `numpy==2.5.4`, and it needs a dozen unused Chinese/Japanese/Korean libraries stubbed out just to import.
    It would need its inference code ported to the image's library versions first. Local use only until then.
  - **Qwen3-TTS** (MLX build) runs on a Mac only and cannot run on Lambda. **VoxCPM2** was rated no. Nothing else is licensed and runnable: Phonon's Spanish voices need a non-commercial model, Amazon
  Polly's Spanish voices (neural Lupe, Pedro; long-form Alba, Raul) have never been run (`-c ttsEngine=polly`, see docs/DEPLOY.md), and
  MeloTTS, Qwen3-TTS and VoxCPM2 are not integrated and have no ratings. Getting to five Spanish voices means a real listening test first.

## Rule: only voices that run in the AWS build too (2026-11-04)
A voice is offered only if it runs in the Lambda image or is an AWS service, so what is tested locally is what ships. That rules out Qwen3-TTS and VoxCPM2 (Mac only) and, until its code is ported
to the image's library versions, MeloTTS. Open-source Piper was also left out for now: its current runtime is GPL-licensed, and only some of its Spanish voices have a clear permissive licence
(its es_MX high-quality voice is Apache-2.0, es_ES "sharvard" is CC BY 3.0).
- **Deployable Spanish candidates:** Kokoro Dora and Alex (in the image today) and Amazon Polly's Spanish voices: neural and generative Lupe, Pedro, Carlos (generative only), Mia, Andrés, Lucia, Sergio,
  and long-form Alba and Raúl. Polly works locally too when the machine has AWS credentials that may call `polly:SynthesizeSpeech`.
- **Next step, once the sandbox is connected:** `python3 scripts/polly_rating_pack.py --dry-run` (14 clips, about $0.33), then run it without `--dry-run`, send the `clips` folder to raters, and keep the key file.
  The winners are then added to `voices.json` as Polly voices chosen by voice id, like the Phonon voices, with a "Hear it" sample each.
