# STT latency and repeatability — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## Method

Measured 10 sequential requests to Teacher's production `POST /v1/speech/transcriptions` endpoint using the configured Groq Whisper STT provider.

To keep the input identical across runs, one fixed WAV fixture was generated once from the sentence:

`I forgot to bring my umbrella yesterday.`

The same WAV bytes were then submitted for all 10 transcription measurements. This isolates STT service latency from human speaking duration or microphone capture variability.

## Results

| Metric | Value |
|---|---:|
| n | 10 |
| Successful responses | 10/10 |
| Mean | 487.4 ms |
| Median | 488.1 ms |
| p95 | 647.4 ms |
| Minimum | 348.0 ms |
| Maximum | 650.9 ms |
| Unique transcripts | 1 |

Observed transcript on all successful runs:

`I forgot to bring my umbrella yesterday.`

## Interpretation

The STT path succeeded on all 10 measured requests with a median latency of about 0.49 s and p95 below 0.65 s. The fixed audio fixture produced one identical transcript across all 10 runs, providing a small repeatability check in addition to the latency measurement.

This benchmark measures the transcription service path itself and does not include microphone recording time; the real microphone interaction path was verified separately during manual target-Mac UAT.

## Evidence status

Aggregate results are recorded here. The corresponding local raw CSV is `report-evidence/experiments/stt-latency.csv`; it still needs to be mirrored to GitHub before the evidence bundle is considered complete.
