Generated 2026-09-04 17:47Z from 11,950 measured books and 8,120 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (liquidity denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 841 | 0.561 | 754,813 | 1.125 | 684,890 |
| CRCLBUSDT | RTH_OPEN | 649 | 0.975 | 766,606 | 2.507 | 698,731 |
| CRCLBUSDT | RTH_POST | 240 | 0.488 | 768,931 | 0.978 | 683,831 |
| CRCLBUSDT | RTH_PRE | 660 | 0.563 | 751,201 | 1.128 | 535,061 |
| MUBUSDT | CLOSED_OVERNIGHT | 841 | 0.310 | 668,006 | 0.783 | 611,256 |
| MUBUSDT | RTH_OPEN | 649 | 0.692 | 653,472 | 1.983 | 573,155 |
| MUBUSDT | RTH_POST | 240 | 0.262 | 810,204 | 0.891 | 777,347 |
| MUBUSDT | RTH_PRE | 660 | 0.579 | 715,016 | 1.297 | 618,552 |
| NVDABUSDT | CLOSED_OVERNIGHT | 841 | 0.435 | 586,474 | 0.887 | 559,282 |
| NVDABUSDT | RTH_OPEN | 649 | 1.090 | 604,809 | 2.197 | 565,550 |
| NVDABUSDT | RTH_POST | 240 | 0.219 | 593,387 | 0.873 | 567,313 |
| NVDABUSDT | RTH_PRE | 660 | 0.891 | 604,309 | 1.953 | 553,518 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 841 | 0.032 | 786,631 | 0.192 | 649,507 |
| SNDKBUSDT | RTH_OPEN | 649 | 0.130 | 790,732 | 1.336 | 668,190 |
| SNDKBUSDT | RTH_POST | 240 | 0.032 | 755,809 | 0.129 | 713,721 |
| SNDKBUSDT | RTH_PRE | 660 | 0.033 | 782,414 | 0.532 | 673,831 |
| TSLABUSDT | CLOSED_OVERNIGHT | 841 | 0.667 | 430,072 | 1.115 | 402,467 |
| TSLABUSDT | RTH_OPEN | 649 | 0.993 | 474,492 | 2.659 | 441,355 |
| TSLABUSDT | RTH_POST | 240 | 0.927 | 451,972 | 2.642 | 425,649 |
| TSLABUSDT | RTH_PRE | 660 | 0.954 | 451,103 | 2.044 | 419,759 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (price-disagreement bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 2,400 | 91.5 | 143.9 | 187.0 | 202.9 |
| RTH_OPEN | 2,547 | 4.4 | 7.6 | 14.7 | 39.3 |
| RTH_POST | 1,200 | 41.9 | 51.3 | 94.0 | 124.5 |
| RTH_PRE | 2,360 | 150.5 | 207.6 | 315.5 | 537.6 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (liquidity sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 841 | 0.5 | 0.8 | 1.3 | 3.1 |
| RTH_OPEN | 649 | 1.0 | 1.3 | 1.9 | 4.1 |
| RTH_POST | 240 | 0.5 | 0.7 | 1.3 | 3.2 |
| RTH_PRE | 660 | 0.8 | 1.1 | 1.7 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** CLOSED_WEEKEND, CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
