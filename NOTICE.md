# Third-party components and content

This project's own code is MIT licensed (see LICENSE). It uses these open-source components. Check each project's
license for the version you install.

| Component | Use | License (as stated by the project; verify) |
|---|---|---|
| Kokoro-82M model and `kokoro` library | Text-to-speech | Apache-2.0 |
| Word photos (`services/synth/word_photos/`, built by `scripts/build_word_photos.py`; also the place pictures in `samples/cards/images/`) | Real photographs on word and place cards, from Wikipedia / Wikimedia Commons. Only CC0, public domain, CC BY and CC BY-SA are used; author and licence are in `services/synth/word_photos.json` and are shown on each card. These files are NOT under the repository MIT licence | CC0, public domain, CC BY, CC BY-SA (per photo) |
| Word definitions (`services/synth/word_definitions.json.gz`, built by `scripts/build_word_definitions.py`) | Definitions, examples and pronunciations on word cards for English passages, trimmed from Open English WordNet 2025 (https://en-word.net), derived from Princeton WordNet. Credit required | CC BY 4.0 |
| Opus-MT `opus-mt-tc-big-en-es` (Helsinki-NLP, revision pinned in `services/synth/translate.py`) | Better English to Spanish translation of passages up to 900 words | CC-BY-4.0 (credit: Helsinki-NLP / OPUS-MT, University of Helsinki) |
| Opus-MT `opus-mt-tc-bible-big-roa-en` (Helsinki-NLP, revision pinned in `services/synth/translate.py`) | Better Spanish to English translation of passages up to 900 words | Apache-2.0 |
| SmolLM2-135M (HuggingFaceTB, revision pinned in `services/synth/possessives.py`) | A tiny English language model that chooses "his", "her" or "their" for Spanish su/sus from the sentences before it (not used to write text) | Apache-2.0 |
| Phonon `phonon-31m-en` model, `gradium/phonon-voices` and the `ptts` runtime | Text-to-speech (voices Hadley and Everly) | Apache-2.0 (runtime: MIT or Apache-2.0) |
| faster-whisper / Whisper models | Word timing for existing human audio; quality checks | MIT |
| UTMOS22 via `tarepan/SpeechMOS` | Predicted naturalness in the quality lab | Check upstream |
| spaCy `en_core_web_sm` | Text processing used by the TTS library | MIT |
| Vue 3, Vite | Web app | MIT |
| Express 4 | API | MIT |
| AWS CDK | Infrastructure as code | Apache-2.0 |

## Content
- `samples/` holds three ReadWorks passages, reduced to title, text and vocabulary. ReadWorks provided them for this
  event as public data (their JSON is served from the public bucket `readworks-media`, under `data/p/<passage-id>`). The text
  belongs to ReadWorks and is used here for a hackathon demonstration only. Answer keys and question sets are not included.
- `samples/5e5f1d3c-7a2b-4c9e-8d1a-3b6f2c9e4a70.json` ("Un día en el parque") is an original passage written for this
  demonstration; it contains no ReadWorks content.
- `samples/cards/*.cards.json` hold word cards (definitions, syllables, examples taken from the passage, Spanish) written for this
  project, and short place descriptions written in our own words from the introductions of the matching Wikipedia articles.
  Wikipedia text is available under CC BY-SA 4.0 (<https://creativecommons.org/licenses/by-sa/4.0/>); each place card credits it, and
  `scripts/fetch_place_summaries.py` shows exactly which articles were read. Word definitions from ReadWorks' own vocabulary data are
  reused only for words ReadWorks already defined. A person must review the cards before students see them
  (`samples/cards/REVIEW.md`).
- `samples/cards/images/` holds small place pictures and location maps from Wikimedia Commons. They are NOT under this repository's MIT licence: each
  keeps its own free licence (CC0, public domain, CC BY or CC BY-SA), is credited on its place card, and CC BY-SA pictures stay under CC BY-SA if you
  reuse them. A person looked at each one before it was accepted (`samples/cards/images.json`).
  - Piedmont Park: Frank Schulenburg, CC BY-SA 4.0, <https://commons.wikimedia.org/wiki/File:Piedmont_Park%E2%80%99s_Lake_Clara_Meer_with_Midtown_Atlanta_skyline_%282024%29-104A8428.jpg>
  - Atlanta: AtlChampion, CC BY-SA 4.0, <https://commons.wikimedia.org/wiki/File:A2ATL20250614-0721_%28cropped%29.jpg>
  - Boston: Ian Howard, CC BY 2.5, <https://commons.wikimedia.org/wiki/File:ISH_WC_Boston4.jpg>
  - Great Britain: Jeff Schmaltz, NASA MODIS Rapid Response Team, Public domain, <https://commons.wikimedia.org/wiki/File:MODIS_-_Great_Britain_-_2012-06-04_during_heat_wave_%28cropped%29.jpg>
  - Hertfordshire: Peter O'Connor aka anemoneprojectors, CC BY-SA 2.0, <https://commons.wikimedia.org/wiki/File:GOC_Hexton_007_Chilterns_landscape_%2824372234911%29_%28cropped%29.jpg>
  - London: Ilya Grigorik, CC BY-SA 3.0, <https://commons.wikimedia.org/wiki/File:London_Skyline_%28125508655%29.jpeg>
  - Georgia: TUBS, CC BY-SA 3.0, <https://commons.wikimedia.org/wiki/File:Georgia_in_United_States.svg>
  - England: Rob, CC BY-SA 3.0, <https://commons.wikimedia.org/wiki/File:England_%28orthographic_projection%29.svg>
  - China: Ssolbergj, CC BY-SA 4.0, <https://commons.wikimedia.org/wiki/File:China_%28orthographic_projection%29.svg>
  - India: Ssolbergj (talk), CC BY-SA 3.0, <https://commons.wikimedia.org/wiki/File:India_%28orthographic_projection%29.svg>
  - North America: Bosonic dressing, CC BY-SA 3.0, <https://commons.wikimedia.org/wiki/File:Location_North_America.svg>
  - Boston Harbor: Beyond My Ken, CC BY-SA 4.0, <https://commons.wikimedia.org/wiki/File:2017_Boston_skyline_from_Boston_Harbor_5_.jpg>
- Headings inside a passage are read aloud (ReadWorks' human recording reads them even though their `text` field omits them).
- ReadWorks' existing human and Polly recordings are NOT stored in this repository. `scripts/build_samples.py`
  downloads them from ReadWorks' public CDN at build time to align and measure them.
- Passage data is public or synthetic. No student data is used.
