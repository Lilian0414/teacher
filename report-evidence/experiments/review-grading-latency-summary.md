# Review grading latency — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## Method

Measured the same review item through `POST /v1/review/{item_id}/retry` so repeated grading would not create attempts or mutate stage/scheduling state.

Two paths were measured with 20 sequential requests each:

- **Deterministic grading**: exact/canonical accepted-answer match; resolved locally by Teacher without invoking the semantic judge.
- **Semantic grading**: paraphrased answer intentionally avoids deterministic matching and therefore exercises the configured Groq semantic grading path.

## Results

| Path | n | Mean | Median | p95 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|
| Deterministic | 20 | 1.0 ms | 0.8 ms | 1.2 ms | 0.8 ms | 4.0 ms |
| Semantic | 20 | 808.2 ms | 760.2 ms | 1169.3 ms | 509.2 ms | 1336.2 ms |

## Interpretation

Teacher's deterministic grading path is effectively local and near-instant at roughly the 1 ms scale. Semantic grading introduces the expected external-model latency, with a median around 0.76 s and a visible long tail above 1.1 s at p95.

This separation is useful for the report because it shows that straightforward answers do not pay the latency cost of an LLM semantic judge; the model is used only when deterministic grading cannot resolve the answer.

## Evidence status

Aggregate results are recorded here. The corresponding local raw CSV is `report-evidence/experiments/review-grading-latency.csv`; it still needs to be mirrored to GitHub before the evidence bundle is considered complete.
