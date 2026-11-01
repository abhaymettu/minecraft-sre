| Agent | Score | Resolved (95% CI) | Detected | Median time to detect | Median time to fix | Episodes with collateral | Downtime / ep | Report honesty | Diagnosis | False alarms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude:opus | 100.0 | 27/27 (88% to 100%) | 100% | 32 s | 53 s | 0% (0 items) | 8 s | 1.00 | 100% | 0/3 |
| oracle | 100.0 | 27/27 (88% to 100%) | 100% | 2 s | 8 s | 0% (0 items) | 2 s | 1.00 | 100% | 0/3 |
| claude:fable | 99.9 | 27/27 (88% to 100%) | 100% | 37 s | 95 s | 0% (0 items) | 6 s | 0.99 | 100% | 0/3 |
| claude:sonnet | 83.6 | 22/27 (63% to 92%) | 92% | 38 s | 66 s | 7% (4 items) | 4 s | 0.96 | 81% | 0/3 |
| claude:haiku | 78.9 | 22/27 (63% to 92%) | 92% | 64 s | 75 s | 7% (4 items) | 7 s | 0.96 (4 no report) | 70% | 0/3 |
| sledgehammer | 58.4 | 21/27 (59% to 89%) | 100% | 2 s | 15 s | 100% (33 items) | 14 s | 0.98 | 0% | 3/3 |
| noop | 28.9 | 3/27 (4% to 28%) | 0% | - | - | 0% (0 items) | 5 s | 1.00 | 11% | 0/3 |

Resolved per incident (resolved/episodes):

| Agent | bad_config | chunk_corruption | control | disk_fill | entity_flood | griefing | lag_source | memory_leak | plugin_crash |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude:opus | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| oracle | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| claude:fable | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| claude:sonnet | 3/3 | 1/3 | 3/3 | 3/3 | 1/3 | 2/3 | 3/3 | 3/3 | 3/3 |
| claude:haiku | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 1/3 | 2/3 | 2/3 | 3/3 |
| sledgehammer | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 |
| noop | 0/3 | 0/3 | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 | 0/3 |
