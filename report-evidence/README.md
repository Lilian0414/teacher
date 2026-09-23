# Teacher report evidence

This directory is the report-writing evidence source for Teacher. It is intentionally separate from feature documentation so scheduled report writers can distinguish measured results from product descriptions.

## Evidence policy

- keep the exact source commit SHA with every measurement;
- retain raw measurements where available, not only aggregates;
- distinguish automated quality checks, manual UAT, performance experiments, and failure/fallback experiments;
- do not commit API keys, private conversation content, personal memory contents, raw user audio, camera frames, or private runtime databases;
- do not claim PASS for a layer that was not actually verified;
- Teacher and Teacher Edge must be described as separate ownership layers: Teacher owns Conversation / Memory / Learning / Review / Proactive domain truth; Teacher Edge owns device transport, runtime, presentation, and physical-device integration.

## Teacher release / quality baseline

Teacher quality/evidence source commit:

`5624e85ebb1ad4a229c63e6a9970c61231403159`

Observed quality gates:

- Ruff: PASS
- strict mypy: PASS on 124 source files
- pytest: 406 passed / 6 skipped
- `git diff --check`: PASS
- isolated Alembic SQLite upgrade/downgrade round trip: PASS
- target-Mac manual UAT: PASS

The Raspberry Pi deployment pin used by Teacher Edge is:

`c1b6a03c1894df2d2b8994cf3b9a124ea8b381e5`

This pin is an integration/deployment baseline and should not be confused with the separate report measurement source commit above.

## Performance experiments

Raw CSVs should be retained whenever available. Current measured summaries:

- conversation latency, n=20: mean 429.1 ms; median 300.0 ms; max 930.6 ms
- review deterministic grading, n=20: mean 1.0 ms; median 0.8 ms; p95 1.2 ms
- review semantic grading, n=20: mean 808.2 ms; median 760.2 ms; p95 1169.3 ms
- memory lexical retrieval, n=20: target found 20/20; mean 0.2 ms
- memory semantic retrieval with local Ollama, n=20: target found 20/20; mean 28.1 ms; p95 32.2 ms
- ElevenLabs TTS, n=10: success 10/10; mean 1854.3 ms; median 1834.1 ms; p95 2028.9 ms
- Groq Whisper STT on a fixed WAV, n=10: success 10/10; mean 487.4 ms; median 488.1 ms; p95 647.4 ms; one unique transcript

Do not convert these component measurements into an unmeasured end-to-end Watcher voice latency.

## Failure / fallback experiments

### Assistant generation failure + retry

Evidence: `experiments/failure-assistant-retry.json`

Verified behavior:

- first assistant generation fails;
- retry succeeds;
- the user turn is not duplicated;
- one user message and one assistant message remain after successful recovery.

Result: **PASS**

### Embedding endpoint unavailable

Evidence: `experiments/failure-embedding-fallback.json`

Observed:

- embedding endpoint intentionally unreachable;
- lexical/person fallback selected;
- target memory still found;
- measured latency: 42.1 ms.

Result: **PASS**

## Manual Teacher UAT

Canonical manual UAT: `doc/FINAL_UAT.md`.

Do not repeat already-passed target-Mac UAT merely to generate more screenshots. New tests should only be added when they prove a new claim or a changed revision.

## Teacher Edge relationship

Teacher Edge evidence lives in `Lilian0414/teacher-edge` and its dedicated evidence branch. As of 2026-09-24, the verified progression is:

- M1.1 Watcher notification ingress + reboot/systemd recovery: PASS
- M1.2 pinned Teacher Core on Raspberry Pi: PASS
- M2 edge → Teacher Core text round-trip and session reuse: PASS
- M3.0 stock Watcher PTT transport/presentation: PASS on PR #15 head `6a6aa096fee2a522cf549a8ae835cf2a191a6d31`
- M3.1 full Watcher voice Teacher conversation (STT → Teacher → ElevenLabs → Watcher): **not yet implemented / not yet UAT passed**

M3.0 specifically proves stock Watcher upload, authenticated edge handling, stock response framing, on-device `screen_text`, and deterministic WAV playback. It does not prove STT, Teacher conversation processing, or provider-backed TTS on that path.

## Safe report-writing claims

Safe high-level statements include:

- Teacher maintains durable learning state across conversation, review, memory, and proactive-practice flows.
- AI providers generate / extract / judge, while deterministic Core services own authorized state mutation.
- Optional AI enrichments can fail without necessarily destroying canonical domain data.
- Teacher has measured component latency and explicit failure/fallback evidence rather than only feature demos.
- Teacher Edge extends the system into a physical Watcher/Pi client while preserving Teacher as the learning-domain source of truth.
- Real hardware has verified M1/M2/M3.0 transport and presentation increments; the complete provider-backed Watcher voice loop remains M3.1.

## Raw evidence still worth mirroring

If still present only locally, mirror these files before treating the evidence branch as archival-complete:

- `experiments/conversation-latency.csv`
- `experiments/review-grading-latency.csv`
- `experiments/memory-retrieval-latency.csv`
- `experiments/tts-latency.csv`
- `experiments/stt-latency.csv`

Do not reconstruct raw rows from summary statistics.
