# TTS latency — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## Method

Measured 10 sequential requests to Teacher's production `POST /v1/speech/synthesis` endpoint using the configured ElevenLabs TTS provider.

Test text:

`Great job. Let's continue with the next question.`

Each latency measurement spans HTTP request submission through receipt of the completed audio response bytes from Core.

## Results

| Metric | Value |
|---|---:|
| n | 10 |
| Successful responses | 10/10 |
| Mean | 1854.3 ms |
| Median | 1834.1 ms |
| p95 | 2028.9 ms |
| Minimum | 1613.3 ms |
| Maximum | 2205.8 ms |

## Interpretation

The TTS path succeeded on all 10 measured requests. Unlike local deterministic grading and local semantic-memory retrieval, speech synthesis depends on an external provider and therefore operates at a seconds-scale latency. The measured median was about 1.83 s and p95 about 2.03 s.

## Evidence status

Aggregate results are recorded here. The corresponding local raw CSV is `report-evidence/experiments/tts-latency.csv`; it still needs to be mirrored to GitHub before the evidence bundle is considered complete.
