# Memory retrieval latency and recall — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## Method

Measured Teacher's production `MemoryContextBuilder.select()` path against the benchmark SQLite database.

Two retrieval modes were measured with 20 sequential runs each:

- **Lexical retrieval**: embedding provider disabled for the builder, so retrieval used local SQLite candidate loading plus lexical/person relevance scoring only.
- **Semantic retrieval**: real local Ollama `nomic-embed-text` embeddings were enabled. The query was intentionally phrased with zero direct lexical overlap against the target memory, and retrieval used Teacher's production hybrid relevance path with cosine similarity.

Target memory:

`Prefers studying late at night with instrumental music.`

Semantic query:

`Which environment improves concentration after sunset?`

The benchmark sanity check reported zero direct word overlap between the target memory and semantic query.

## Results

| Path | n | Target found | Mean | Median | p95 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lexical | 20 | 20/20 | 0.2 ms | 0.2 ms | 0.2 ms | 0.1 ms | 0.3 ms |
| Semantic | 20 | 20/20 | 28.1 ms | 28.1 ms | 32.2 ms | 23.9 ms | 34.8 ms |

## Interpretation

Local lexical retrieval is effectively instantaneous at this benchmark scale. The semantic path adds the cost of generating a query embedding through local Ollama, but still completed in roughly 28 ms median and retrieved the intended memory in all 20 runs despite zero direct lexical overlap.

This provides two distinct pieces of evidence for the report:

1. semantic memory recall works beyond direct keyword overlap;
2. the local embedding-based recall path remains low-latency on the target Mac.

## Evidence status

Aggregate results are recorded here. The corresponding local raw CSV is `report-evidence/experiments/memory-retrieval-latency.csv`; it still needs to be mirrored to GitHub before the evidence bundle is considered complete.
