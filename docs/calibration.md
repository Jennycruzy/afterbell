Generated 2026-09-08 09:11Z from 38,185 measured books and 34,345 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (liquidity denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_HOLIDAY | 1,440 | 0.490 | 479,299 | 0.982 | 402,600 |
| CRCLBUSDT | CLOSED_OVERNIGHT | 1,081 | 0.560 | 751,188 | 1.124 | 684,890 |
| CRCLBUSDT | CLOSED_WEEKEND | 3,120 | 0.491 | 750,556 | 0.984 | 455,821 |
| CRCLBUSDT | RTH_OPEN | 781 | 0.510 | 763,467 | 2.460 | 699,980 |
| CRCLBUSDT | RTH_POST | 480 | 0.492 | 809,383 | 0.978 | 710,374 |
| CRCLBUSDT | RTH_PRE | 735 | 0.561 | 747,445 | 1.127 | 537,267 |
| MUBUSDT | CLOSED_HOLIDAY | 1,440 | 0.096 | 689,830 | 0.670 | 436,762 |
| MUBUSDT | CLOSED_OVERNIGHT | 1,081 | 0.314 | 670,055 | 0.793 | 613,022 |
| MUBUSDT | CLOSED_WEEKEND | 3,120 | 0.146 | 456,932 | 0.784 | 358,522 |
| MUBUSDT | RTH_OPEN | 781 | 0.635 | 657,118 | 1.874 | 577,332 |
| MUBUSDT | RTH_POST | 480 | 0.209 | 759,558 | 0.887 | 629,837 |
| MUBUSDT | RTH_PRE | 735 | 0.615 | 711,573 | 1.359 | 608,119 |
| NVDABUSDT | CLOSED_HOLIDAY | 1,440 | 0.216 | 581,795 | 0.648 | 548,362 |
| NVDABUSDT | CLOSED_OVERNIGHT | 1,081 | 0.431 | 588,728 | 0.870 | 560,339 |
| NVDABUSDT | CLOSED_WEEKEND | 3,120 | 0.217 | 589,907 | 0.649 | 560,069 |
| NVDABUSDT | RTH_OPEN | 781 | 1.099 | 601,868 | 2.179 | 566,699 |
| NVDABUSDT | RTH_POST | 480 | 0.218 | 592,124 | 0.655 | 568,773 |
| NVDABUSDT | RTH_PRE | 735 | 0.885 | 603,379 | 1.948 | 554,229 |
| SNDKBUSDT | CLOSED_HOLIDAY | 1,440 | 0.028 | 876,809 | 0.223 | 697,480 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 1,081 | 0.032 | 787,390 | 0.259 | 651,088 |
| SNDKBUSDT | CLOSED_WEEKEND | 3,120 | 0.028 | 821,491 | 0.375 | 681,817 |
| SNDKBUSDT | RTH_OPEN | 781 | 0.226 | 822,895 | 1.307 | 672,872 |
| SNDKBUSDT | RTH_POST | 480 | 0.032 | 742,193 | 0.693 | 701,420 |
| SNDKBUSDT | RTH_PRE | 735 | 0.033 | 802,253 | 0.679 | 674,654 |
| TSLABUSDT | CLOSED_HOLIDAY | 1,440 | 0.423 | 505,456 | 1.126 | 440,628 |
| TSLABUSDT | CLOSED_OVERNIGHT | 1,081 | 0.561 | 436,796 | 1.088 | 404,955 |
| TSLABUSDT | CLOSED_WEEKEND | 3,120 | 0.281 | 516,315 | 0.984 | 458,959 |
| TSLABUSDT | RTH_OPEN | 781 | 0.991 | 478,860 | 2.630 | 443,672 |
| TSLABUSDT | RTH_POST | 480 | 0.662 | 482,965 | 2.380 | 431,020 |
| TSLABUSDT | RTH_PRE | 735 | 0.850 | 453,930 | 2.026 | 420,254 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (price-disagreement bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| CLOSED_HOLIDAY | 7,200 | 90.5 | 247.2 | 293.9 | 378.0 |
| CLOSED_OVERNIGHT | 3,600 | 102.0 | 161.0 | 274.7 | 384.6 |
| CLOSED_WEEKEND | 15,600 | 48.8 | 111.5 | 250.2 | 293.5 |
| RTH_OPEN | 3,207 | 4.5 | 7.1 | 12.6 | 33.9 |
| RTH_POST | 2,400 | 37.2 | 47.6 | 79.9 | 110.9 |
| RTH_PRE | 2,725 | 140.2 | 205.0 | 310.1 | 532.3 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (liquidity sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_HOLIDAY | 1,440 | 0.4 | 0.6 | 1.2 | 3.5 |
| CLOSED_OVERNIGHT | 1,081 | 0.5 | 0.8 | 1.3 | 3.2 |
| CLOSED_WEEKEND | 3,120 | 0.4 | 0.5 | 1.1 | 3.4 |
| RTH_OPEN | 781 | 1.0 | 1.2 | 1.8 | 3.8 |
| RTH_POST | 480 | 0.4 | 0.5 | 1.0 | 2.6 |
| RTH_PRE | 735 | 0.8 | 1.1 | 1.7 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.
