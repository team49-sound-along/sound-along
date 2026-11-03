# Sound Along file format (for ReadWorks' frontend)

ReadWorks' passages are one product JSON document each, with audio referenced by id (`au`) and capabilities listed in `features` (for example `["au","hau","qsmw"]`, where `hau` marks a human recording). Sound Along adds one more file per passage with the same shape of thinking: **a `soundAlong` block to merge into the product JSON, plus the audio and timing files it references.** The frontend does no processing beyond presenting these.

## Files per passage (S3 `data/`)
| File | Content |
|---|---|
| `{id}.soundalong.json` | The block below. Merge `soundAlong` into the product JSON and add the listed `features`. |
| `{voiceId}.mp3` | Constant-bitrate mono MP3 (seeks accurately; default 48 kbps). One per voice. |
| `{voiceId}.timing.json` | Word timing for that voice (below). |

## `{id}.soundalong.json`
```json
{
  "soundAlong": {
    "version": 1,
    "passageId": "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98",
    "defaultVoice": "human",
    "voices": [
      { "kind": "human", "audio": "181b9f7b-6e16-57ce-bec2-a48c90d591d0", "timing": "181b9f7b-6e16-57ce-bec2-a48c90d591d0.timing.json",
        "engine": "human", "voice": "ReadWorks narrator", "durationMs": 115602 },
      { "kind": "ai", "audio": "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98", "timing": "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.timing.json",
        "engine": "kokoro", "voice": "af_heart", "durationMs": 136500 }
    ]
  },
  "features": ["sa", "sahv"]
}
```
- `voices` lists the human voice first when a recording exists; `defaultVoice` is the first entry.
- `audio` is an id, resolved to `{id}.mp3`, in the same way `au` is resolved to a CDN URL today.
- Feature flags: `sa` = Sound Along available; `sahv` = it also has a human-voice variant.

## `{voiceId}.timing.json`
```json
{
  "id": "...", "title": "...", "language": "en", "engine": "kokoro", "voice": "af_heart", "pairId": "<other voice's id> (optional)",
  "duration_ms": 136500,
  "vocab": { "<senseId>": { "word": "nature", "definition": "...", "partOfSpeech": "noun", "examples": ["..."], "spanish": ["naturaleza"] } },
  "words": [ { "i": 0, "text": "Lots", "start_ms": 275, "end_ms": 600, "sentence": 0, "paragraph": 0, "aligned": true, "vocabId": "2753102" } ],
  "review": { "source": "asr-check", "suspects": [ { "expected": "gaieties", "heard": "deities" } ] },
  "generatedWith": { "settings": { "voice": "af_heart", "speed": 0.95, "mp3Kbps": 48 }, "pronunciations": { "gaieties": "gayetees" } },
  "metrics": { "...": "generation counts, speed and cost estimates" }
}
```
- `words` come from the passage's rendered HTML, one entry per displayed word, with a stable index `i`. Figures, captions and credits are skipped. A dash joins no words ("good—and" is two entries).
- `aligned: false` means the time is estimated (the recognizer did not match the word); the reader disables "Hear this word" for it.
- In S3 the timing file is stored gzipped with `Content-Encoding: gzip`, so `fetch()` returns the JSON unchanged.
- `language` is `en` or `es`. Spanish word times come from a speech-recognition pass (Kokoro gives none for Spanish), so they are
  recognizer-derived and have no independent check.

## What the frontend does
1. Read the product JSON; if `features` contains `sa`, read `{id}.soundalong.json`'s `soundAlong`.
2. Load the chosen voice's `.timing.json` and `.mp3`.
3. On `requestAnimationFrame`, binary-search `words` by `audio.currentTime`; tapping a word sets `currentTime` to its `start_ms`.
