# Third-party components and content

This project's own code is MIT licensed (see LICENSE). It uses these open-source components. Check each project's
license for the version you install.

| Component | Use | License (as stated by the project; verify) |
|---|---|---|
| Kokoro-82M model and `kokoro` library | Text-to-speech | Apache-2.0 |
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
- Headings inside a passage are read aloud (ReadWorks' human recording reads them even though their `text` field omits them).
- ReadWorks' existing human and Polly recordings are NOT stored in this repository. `scripts/build_samples.py`
  downloads them from ReadWorks' public CDN at build time to align and measure them.
- Passage data is public or synthetic. No student data is used.
