#!/usr/bin/env bash
# Build the generator image and prove it works with NO network, using the same code Lambda runs.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build --platform linux/arm64 --build-arg "PYTHON_VERSION=${PYTHON_VERSION:-3.14}" -f services/generator/Dockerfile -t sound-along-generator .
docker run --rm --network none -e PYTHONPATH=/var/task:/var/task/synth:/var/task/parse --entrypoint python sound-along-generator -c "
import handler  # the real Lambda entry module must import cleanly
from pipeline import generate
from engines import create_engine
engine = create_engine('kokoro')
result = generate('<p>The gaieties were good—and fun. We saw 3 birds.</p>', engine)
assert result.words, 'no words produced'
assert result.unaligned_words == 0, f'{result.unaligned_words} unaligned words'
assert [w['text'] for w in result.words][2:4] == ['were', 'good—'], 'em-dash was not split'
# every selectable voice must be baked in, and the recognizer must run offline too
for voice in ('af_bella', 'bm_george'):
    out = create_engine('kokoro', settings={'voice': voice}).synthesize('Hello there.')
    assert len(out.audio) > 0, voice
from asr_words import resample_to_16k, transcribe
from engine import SAMPLE_RATE
heard = transcribe(resample_to_16k(result.audio, SAMPLE_RATE))
assert any(h.text.strip('.,').lower() == 'birds' for h in heard), [h.text for h in heard]
print('OK: handler imports, offline synthesis, 2 extra voices, offline recognition;', len(result.words), 'words, 0 unaligned')
"
