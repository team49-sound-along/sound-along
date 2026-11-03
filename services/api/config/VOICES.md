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
- Phonon is English only here (Spanish models are non-commercial), and it is not wired in yet.
