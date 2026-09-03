Generated 2026-09-03 19:43Z from 5,325 measured books and 1,507 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

### Session baselines (P2 denominators)

| Symbol | State | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 361 | 0.563 | 759,510 | 1.126 | 676,761 |
| CRCLBUSDT | RTH_OPEN | 374 | 0.977 | 771,395 | 2.504 | 707,485 |
| CRCLBUSDT | RTH_PRE | 330 | 1.095 | 726,373 | 1.126 | 507,560 |
| MUBUSDT | CLOSED_OVERNIGHT | 361 | 0.314 | 652,633 | 0.891 | 604,350 |
| MUBUSDT | RTH_OPEN | 374 | 0.794 | 622,353 | 2.209 | 565,952 |
| MUBUSDT | RTH_PRE | 330 | 0.708 | 703,193 | 1.423 | 612,797 |
| NVDABUSDT | CLOSED_OVERNIGHT | 361 | 0.443 | 582,910 | 1.110 | 557,807 |
| NVDABUSDT | RTH_OPEN | 374 | 1.089 | 601,920 | 2.214 | 563,562 |
| NVDABUSDT | RTH_PRE | 330 | 1.107 | 597,559 | 2.004 | 548,904 |
| SNDKBUSDT | CLOSED_OVERNIGHT | 361 | 0.032 | 679,883 | 0.194 | 635,678 |
| SNDKBUSDT | RTH_OPEN | 374 | 0.128 | 749,849 | 0.992 | 668,139 |
| SNDKBUSDT | RTH_PRE | 330 | 0.033 | 718,458 | 0.423 | 652,757 |
| TSLABUSDT | CLOSED_OVERNIGHT | 361 | 0.557 | 425,234 | 0.978 | 396,194 |
| TSLABUSDT | RTH_OPEN | 374 | 0.918 | 467,697 | 2.647 | 444,624 |
| TSLABUSDT | RTH_PRE | 330 | 0.828 | 447,034 | 1.525 | 414,557 |

**Status: CALIBRATED.** Every symbol has at least 300 RTH_OPEN samples.

### Basis distribution by state (P3 bands)

| State | n | p50 \|basis\| | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| RTH_OPEN | 1,172 | 3.8 | 7.7 | 23.4 | 48.2 |
| RTH_PRE | 710 | 77.1 | 138.0 | 257.8 | 319.8 |

Bands are proposed at empirical percentiles — WATCH at p75, DEGRADED at p95, BROKEN at p99 — rather than at round numbers.

### Walk-cost curve (P2 sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| CLOSED_OVERNIGHT | 361 | 0.6 | 0.8 | 1.2 | 3.3 |
| RTH_OPEN | 374 | 1.0 | 1.3 | 1.9 | 5.0 |
| RTH_PRE | 330 | 0.8 | 1.1 | 1.5 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.

**Not yet observed:** CLOSED_WEEKEND, CLOSED_HOLIDAY. These rows appear once the recorder has lived through them; they are not estimated from the states that were.
