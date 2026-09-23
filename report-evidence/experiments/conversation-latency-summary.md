# Conversation latency — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## Method

Measured 20 sequential end-to-end HTTP requests against the benchmark Core endpoint for a normal conversation message. Each measurement spans request submission through the completed assistant response returned by Core, including the configured Groq assistant path.

This is request-level end-to-end server latency, not UI rendering latency.

## Results

| Metric | Value |
|---|---:|
| n | 20 |
| Mean | 429.1 ms |
| Median | 300.0 ms |
| Minimum | 204.0 ms |
| Maximum | 930.6 ms |

Interpretation: the median response was about 300 ms, while the mean was higher because the run contained a noticeable long tail, with the slowest request reaching about 931 ms.

## Evidence status

Aggregate results are recorded here. The corresponding local raw CSV is `report-evidence/experiments/conversation-latency.csv`; it still needs to be mirrored to GitHub before the evidence bundle is considered complete.
