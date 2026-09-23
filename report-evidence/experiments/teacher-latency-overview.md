# Teacher latency overview — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

This file summarizes the measured Teacher latency paths collected on the target Mac. Detailed methodology and raw-data locations are documented in the per-experiment files.

| Path | n | Median | p95 | Success / recall |
|---|---:|---:|---:|---:|
| Memory lexical retrieval | 20 | 0.2 ms | 0.2 ms | 20/20 |
| Review deterministic grading | 20 | 0.8 ms | 1.2 ms | measured path completed |
| Memory semantic retrieval (local Ollama) | 20 | 28.1 ms | 32.2 ms | 20/20 |
| Conversation response | 20 | 300.0 ms | not yet derived from raw CSV | measured path completed |
| STT transcription (Groq Whisper) | 10 | 488.1 ms | 647.4 ms | 10/10 |
| Review semantic grading (Groq) | 20 | 760.2 ms | 1169.3 ms | measured path completed |
| TTS synthesis (ElevenLabs) | 10 | 1834.1 ms | 2028.9 ms | 10/10 |

## Reading the results

The measurements separate local deterministic work, local semantic retrieval, and external AI service calls.

- Local deterministic grading and lexical retrieval operate at sub-millisecond to roughly 1 ms scale.
- Local semantic-memory retrieval with Ollama remains in the tens-of-milliseconds range.
- Groq-backed conversation/STT/semantic grading paths operate in the hundreds-of-milliseconds range.
- ElevenLabs TTS is the slowest measured path, operating around the 2-second scale.

These results should be presented as measured behavior on the target Mac and configured providers, not as universal service-level guarantees.

## Supporting files

- `conversation-latency-summary.md`
- `review-grading-latency-summary.md`
- `memory-retrieval-latency-summary.md`
- `stt-latency-summary.md`
- `tts-latency-summary.md`

Raw CSV files are currently collected locally under `report-evidence/experiments/` and should be mirrored before final evidence sign-off.
