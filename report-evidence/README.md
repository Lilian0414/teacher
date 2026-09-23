# Teacher report evidence

This directory collects reproducible evidence for the Teacher / Teacher Edge graduate-application results report.

Evidence policy:

- keep the exact source commit SHA with every measurement;
- retain raw measurements where available, not only aggregates;
- distinguish automated quality checks, manual UAT, performance experiments, and failure/fallback experiments;
- do not commit API keys, private conversation content, personal memory contents, audio, camera frames, or private runtime databases;
- do not claim PASS for a layer that was not actually verified.

Current measurement baseline:

- Teacher source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`
- target platform: macOS / arm64 / Python 3.12
- manual target-Mac UAT: passed
- quality gates: Ruff passed; strict mypy passed on 124 source files; pytest 406 passed / 6 skipped; Alembic SQLite round trip passed

The local raw evidence bundle under `report-evidence/` should be mirrored here before this evidence branch is treated as complete.
