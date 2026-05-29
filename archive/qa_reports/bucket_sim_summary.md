# AICOS Bucket Simulation Summary

- Generated at: `2026-04-25T09:42:27.134713`
- Mode: `mock_extract`
- Fixtures: `tests/fixtures/aicos_bucket_sim_fixtures.json`
- Status: **PASS**

## Metrics
- Total cases: **200**
- Filter accuracy: **100.0%** (threshold 90.0%)
- Bucket exact-match accuracy: **99.41%** (threshold 85.0%)
- Task-like cases (bucket-evaluated): **170**
- Total mismatches: **1**

## Per-Bucket Precision/Recall
- DO NOW: precision 100.0% | recall 100.0% | tp 39 fp 0 fn 0
- SCHEDULE: precision 100.0% | recall 100.0% | tp 30 fp 0 fn 0
- DELEGATE: precision 100.0% | recall 100.0% | tp 39 fp 0 fn 0
- REVIEW LATER: precision 100.0% | recall 96.88% | tp 31 fp 0 fn 1
- ELIMINATE: precision 96.77% | recall 100.0% | tp 30 fp 1 fn 0

## Top Mismatches By Reason
### bucket_mismatch
- `edge_noise_with_action_word` expected `REVIEW LATER` got `ELIMINATE` | Newsletter reminder
