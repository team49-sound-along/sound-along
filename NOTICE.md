# Third-party components and content

This project's own code is MIT licensed (see LICENSE). It uses these open-source components. Check each project's
license for the version you install.

| Component | Use | License (as stated by the project; verify) |
|---|---|---|
| Kokoro-82M model and `kokoro` library | Text-to-speech | Apache-2.0 |
| faster-whisper / Whisper models | Word timing for existing human audio; quality checks | MIT |
| UTMOS22 via `tarepan/SpeechMOS` | Predicted naturalness in the quality lab | Check upstream |
| spaCy `en_core_web_sm` | Text processing used by the TTS library | MIT |
| Vue 3, Vite | Web app | MIT |
| Express 4 | API | MIT |
| AWS CDK | Infrastructure as code | Apache-2.0 |

## Content
- `samples/` holds three public ReadWorks passages, reduced to title, text and vocabulary. The text belongs to
  ReadWorks and is used here for a hackathon demonstration only. Answer keys and question sets are not included.
- ReadWorks' existing human and Polly recordings are NOT stored in this repository. `scripts/build_samples.py`
  downloads them from ReadWorks' public CDN at build time to align and measure them.
- Passage data is public or synthetic. No student data is used.
