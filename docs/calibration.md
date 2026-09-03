Generated 2026-09-03 11:33Z from 2,870 measured books and 120 reference prints. Depth band ±1%.

### Session baselines (P2 denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 361 | 0.563 | 759,510 | 1.126 | 676,761 |
| CRCLBUSDT | RTH_PRE | 213 | 1.113 | 688,364 | 1.127 | 491,611 |
| MUBUSDT | CLOSED_OVERNIGHT | 361 | 0.314 | 652,633 | 0.891 | 604,350 |
| MUBUSDT | RTH_PRE | 213 | 0.736 | 712,194 | 1.422 | 616,654 |
| NVDABUSDT | CLOSED_OVERNIGHT | 361 | 0.443 | 582,910 | 1.110 | 557,807 |
| NVDABUSDT | RTH_PRE | 213 | 1.109 | 596,780 | 2.005 | 546,849 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 361 | 0.032 | 679,883 | 0.194 | 635,678 |
| SNDKBUSDT | RTH_PRE | 213 | 0.033 | 709,959 | 0.357 | 632,757 |
| TSLABUSDT | CLOSED_OVERNIGHT | 361 | 0.557 | 425,234 | 0.978 | 396,194 |
| TSLABUSDT | RTH_PRE | 213 | 0.694 | 452,123 | 1.387 | 426,487 |

**Status: UNCALIBRATED.** P2's denominators are RTH_OPEN medians and 5 of 5 symbols are below the 300-sample minimum (CRCLBUSDT 0, MUBUSDT 0, NVDABUSDT 0, SNDKBUSDT 0, TSLABUSDT 0). Those symbols receive the most restrictive tier and are not quietly compared against a baseline built from too little data.

### Basis distribution by state (P3 bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| RTH_PRE | 125 | 71.9 | 90.8 | 140.2 | 150.7 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (P2 sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 361 | 0.6 | 0.8 | 1.2 | 3.3 |
| RTH_PRE | 213 | 0.8 | 1.1 | 1.6 | 3.9 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** RTH_OPEN, CLOSED_WEEKEND, CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
