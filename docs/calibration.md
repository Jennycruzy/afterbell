Generated 2026-09-05 13:50Z from 17,965 measured books and 14,135 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (liquidity denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 841 | 0.561 | 754,813 | 1.125 | 684,890 |
| CRCLBUSDT | CLOSED_WEEKEND | 831 | 0.492 | 789,821 | 0.986 | 443,741 |
| CRCLBUSDT | RTH_OPEN | 781 | 0.510 | 763,467 | 2.460 | 699,980 |
| CRCLBUSDT | RTH_POST | 480 | 0.492 | 809,383 | 0.978 | 710,374 |
| CRCLBUSDT | RTH_PRE | 660 | 0.563 | 751,201 | 1.128 | 535,061 |
| MUBUSDT | CLOSED_OVERNIGHT | 841 | 0.310 | 668,006 | 0.783 | 611,256 |
| MUBUSDT | CLOSED_WEEKEND | 831 | 0.246 | 505,150 | 0.788 | 411,845 |
| MUBUSDT | RTH_OPEN | 781 | 0.635 | 657,118 | 1.874 | 577,332 |
| MUBUSDT | RTH_POST | 480 | 0.209 | 759,558 | 0.887 | 629,837 |
| MUBUSDT | RTH_PRE | 660 | 0.579 | 715,016 | 1.297 | 618,552 |
| NVDABUSDT | CLOSED_OVERNIGHT | 841 | 0.435 | 586,474 | 0.887 | 559,282 |
| NVDABUSDT | CLOSED_WEEKEND | 831 | 0.217 | 605,309 | 0.434 | 576,141 |
| NVDABUSDT | RTH_OPEN | 781 | 1.099 | 601,868 | 2.179 | 566,699 |
| NVDABUSDT | RTH_POST | 480 | 0.218 | 592,124 | 0.655 | 568,773 |
| NVDABUSDT | RTH_PRE | 660 | 0.891 | 604,309 | 1.953 | 553,518 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 841 | 0.032 | 786,631 | 0.192 | 649,507 |
| SNDKBUSDT | CLOSED_WEEKEND | 831 | 0.029 | 727,067 | 0.598 | 650,519 |
| SNDKBUSDT | RTH_OPEN | 781 | 0.226 | 822,895 | 1.307 | 672,872 |
| SNDKBUSDT | RTH_POST | 480 | 0.032 | 742,193 | 0.693 | 701,420 |
| SNDKBUSDT | RTH_PRE | 660 | 0.033 | 782,414 | 0.532 | 673,831 |
| TSLABUSDT | CLOSED_OVERNIGHT | 841 | 0.667 | 430,072 | 1.115 | 402,467 |
| TSLABUSDT | CLOSED_WEEKEND | 831 | 0.282 | 475,502 | 0.845 | 448,076 |
| TSLABUSDT | RTH_OPEN | 781 | 0.991 | 478,860 | 2.630 | 443,672 |
| TSLABUSDT | RTH_POST | 480 | 0.662 | 482,965 | 2.380 | 431,020 |
| TSLABUSDT | RTH_PRE | 660 | 0.954 | 451,103 | 2.044 | 419,759 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (price-disagreement bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 2,400 | 91.5 | 143.9 | 187.0 | 202.9 |
| CLOSED_WEEKEND | 4,155 | 30.9 | 55.9 | 120.0 | 178.1 |
| RTH_OPEN | 3,207 | 4.5 | 7.1 | 12.6 | 33.9 |
| RTH_POST | 2,400 | 37.2 | 47.6 | 79.9 | 110.9 |
| RTH_PRE | 2,360 | 150.5 | 207.6 | 315.5 | 537.6 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (liquidity sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 841 | 0.5 | 0.8 | 1.3 | 3.1 |
| CLOSED_WEEKEND | 831 | 0.3 | 0.5 | 0.9 | 2.9 |
| RTH_OPEN | 781 | 1.0 | 1.2 | 1.8 | 3.8 |
| RTH_POST | 480 | 0.4 | 0.5 | 1.0 | 2.6 |
| RTH_PRE | 660 | 0.8 | 1.1 | 1.7 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
