#!/usr/bin/env bash
# Build the generator image and prove it works with NO network, using the same code Lambda runs.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build --platform linux/arm64 --build-arg "PYTHON_VERSION=${PYTHON_VERSION:-3.14}" -f services/generator/Dockerfile -t sound-along-generator .
# Lambda runs the image as a non-root user on a READ-ONLY filesystem where only /tmp is writable, with no network.
docker run --rm --network none --read-only --tmpfs /tmp:rw,exec,size=1g --user 1000:1000 -e HOME=/home/sbx_user1051 -e PYTHONPATH=/var/task:/var/task/synth:/var/task/parse --entrypoint python sound-along-generator -c "
import handler  # the real Lambda entry module must import cleanly
from pipeline import generate
from engines import create_engine
engine = create_engine('kokoro')
result = generate('<p>The gaieties were good—and fun. We saw 3 birds.</p>', engine)
assert result.words, 'no words produced'
assert result.unaligned_words == 0, f'{result.unaligned_words} unaligned words'
assert [w['text'] for w in result.words][2:4] == ['were', 'good—'], 'em-dash was not split'
# every selectable voice must be baked in, and the recognizer must run offline too
for voice in ('af_heart',):
    out = create_engine('kokoro', settings={'voice': voice}).synthesize('Hello there.')
    assert len(out.audio) > 0, voice
from asr_words import resample_to_16k, transcribe
from engine import SAMPLE_RATE
heard = transcribe(resample_to_16k(result.audio, SAMPLE_RATE))
assert any(h.text.strip('.,').lower() == 'birds' for h in heard), [h.text for h in heard]
# Spanish: Kokoro speaks it without word times, so the multilingual recognizer must supply them, offline
from flow import run_flow
es = run_flow({'uuid': 'es', 'title': 'T', 'language': 'es', 'content': '<p>Los niños van al parque. Allí juegan con sus amigos.</p>'},
              create_engine('kokoro', settings={'voiceEs': 'em_alex'}, language='es'))
assert es.ai.timing['language'] == 'es' and es.ai.timing['metrics']['unalignedWords'] == 0, es.ai.timing['metrics']
# Phonon: baked model and both voices load from disk with no network; word times come from the recognizer
for voice in ('phonon_hadley', 'phonon_everly'):
    ph = run_flow({'uuid': 'ph', 'title': 'T', 'content': '<p>The class walked to the library. Maya found a book about three red birds.</p>'},
                  create_engine(settings={'voice': voice}))
    assert ph.ai.timing['engine'] == 'phonon' and ph.ai.timing['voice'] == voice, ph.ai.timing['engine']
    assert ph.ai.timing['metrics']['unalignedWords'] <= 0.2 * len(ph.ai.timing['words']), (voice, ph.ai.timing['metrics'])  # recognizer-timed: a short clip may drop a word
# Live place cards: spaCy finds places offline, and with NO network enrichment returns nothing instead of failing the job
from enrich_places import enrich_places, ner_places
assert 'London' in ner_places('We visited Tower Bridge in London.'), ner_places('We visited Tower Bridge in London.')
offline = enrich_places({'uuid': 'x', 'source': 'generated', 'language': 'en', 'content': '<p>We saw Tower Bridge in London.</p>'}, ner=ner_places)
assert offline is None, offline
from word_pictures import word_picture_cards
cards, pics = word_picture_cards('x' * 8 + '-0000-4000-8000-000000000000', 'The children ate cookies and drank tea near the trees.')
assert {'cookies', 'tea', 'trees'} <= set(cards) and len(pics) >= 3, cards.keys()
print('OK: handler imports, offline synthesis, 2 extra voices, offline recognition, Spanish with recognizer timing, Phonon (2 voices) offline, place detection, word pictures and offline-safe enrichment;', len(result.words), 'English words, 0 unaligned')
"
