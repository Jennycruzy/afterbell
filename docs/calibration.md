Generated 2026-09-08 13:07Z from 39,365 measured books and 35,520 reference prints. Depth band ±1%; baseline window: rolling 7-day window.

**Reader note:** this report shows whether the recorded data is deep enough to compare current conditions with normal conditions. The dashboard uses these measurements to explain the current order limit.

### Normal market conditions (liquidity baselines)

| Symbol | Market period | n | Median half-spread (bps) | Median depth ±1% (USDT) | p95 half-spread | p05 depth |
|---|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | Market holiday | 1,440 | 0.490 | 479,299 | 0.982 | 402,600 |
| CRCLBUSDT | Overnight closure | 1,081 | 0.560 | 751,188 | 1.124 | 684,890 |
| CRCLBUSDT | Weekend closure | 3,120 | 0.491 | 750,556 | 0.984 | 455,821 |
| CRCLBUSDT | Open | 781 | 0.510 | 763,467 | 2.460 | 699,980 |
| CRCLBUSDT | After close | 480 | 0.492 | 809,383 | 0.978 | 710,374 |
| CRCLBUSDT | Before open | 971 | 0.557 | 749,872 | 1.126 | 556,614 |
| MUBUSDT | Market holiday | 1,440 | 0.096 | 689,830 | 0.670 | 436,762 |
| MUBUSDT | Overnight closure | 1,081 | 0.314 | 670,055 | 0.793 | 613,022 |
| MUBUSDT | Weekend closure | 3,120 | 0.146 | 456,932 | 0.784 | 358,522 |
| MUBUSDT | Open | 781 | 0.635 | 657,118 | 1.874 | 577,332 |
| MUBUSDT | After close | 480 | 0.209 | 759,558 | 0.887 | 629,837 |
| MUBUSDT | Before open | 971 | 0.633 | 699,466 | 1.314 | 611,463 |
| NVDABUSDT | Market holiday | 1,440 | 0.216 | 581,795 | 0.648 | 548,362 |
| NVDABUSDT | Overnight closure | 1,081 | 0.431 | 588,728 | 0.870 | 560,339 |
| NVDABUSDT | Weekend closure | 3,120 | 0.217 | 589,907 | 0.649 | 560,069 |
| NVDABUSDT | Open | 781 | 1.099 | 601,868 | 2.179 | 566,699 |
| NVDABUSDT | After close | 480 | 0.218 | 592,124 | 0.655 | 568,773 |
| NVDABUSDT | Before open | 971 | 0.649 | 602,252 | 1.781 | 558,354 |
| SNDKBUSDT | Market holiday | 1,440 | 0.028 | 876,809 | 0.223 | 697,480 |
| SNDKBUSDT | Overnight closure | 1,081 | 0.032 | 787,390 | 0.259 | 651,088 |
| SNDKBUSDT | Weekend closure | 3,120 | 0.028 | 821,491 | 0.375 | 681,817 |
| SNDKBUSDT | Open | 781 | 0.226 | 822,895 | 1.307 | 672,872 |
| SNDKBUSDT | After close | 480 | 0.032 | 742,193 | 0.693 | 701,420 |
| SNDKBUSDT | Before open | 971 | 0.062 | 835,892 | 0.679 | 681,175 |
| TSLABUSDT | Market holiday | 1,440 | 0.423 | 505,456 | 1.126 | 440,628 |
| TSLABUSDT | Overnight closure | 1,081 | 0.561 | 436,796 | 1.088 | 404,955 |
| TSLABUSDT | Weekend closure | 3,120 | 0.281 | 516,315 | 0.984 | 458,959 |
| TSLABUSDT | Open | 781 | 0.991 | 478,860 | 2.630 | 443,672 |
| TSLABUSDT | After close | 480 | 0.662 | 482,965 | 2.380 | 431,020 |
| TSLABUSDT | Before open | 971 | 0.828 | 459,140 | 1.802 | 420,611 |

**Data coverage: complete.** Every symbol has at least 300 regular-hours samples.

### Basis distribution by state (price-disagreement bands)

| Market period | n | p50 absolute difference | p75 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| Market holiday | 7,200 | 90.5 | 247.2 | 293.9 | 378.0 |
| Overnight closure | 3,600 | 102.0 | 161.0 | 274.7 | 384.6 |
| Weekend closure | 15,600 | 48.8 | 111.5 | 250.2 | 293.5 |
| Open | 3,207 | 4.5 | 7.1 | 12.6 | 33.9 |
| After close | 2,400 | 37.2 | 47.6 | 79.9 | 110.9 |
| Before open | 3,900 | 130.3 | 193.4 | 295.3 | 507.1 |

The proposed bands use measured percentiles: caution at p75, elevated at p95, and blocked at p99, rather than arbitrary round numbers.

### Walk-cost curve (liquidity sizing)

| State | n | $100 | $500 | $2,000 | $10,000 |
|---|---:|---:|---:|---:|---:|
| Market holiday | 1,440 | 0.4 | 0.6 | 1.2 | 3.5 |
| Overnight closure | 1,081 | 0.5 | 0.8 | 1.3 | 3.2 |
| Weekend closure | 3,120 | 0.4 | 0.5 | 1.1 | 3.4 |
| Open | 781 | 1.0 | 1.2 | 1.8 | 3.8 |
| After close | 480 | 0.4 | 0.5 | 1.0 | 2.6 |
| Before open | 971 | 0.7 | 1.0 | 1.6 | 3.7 |

Median cost in bps to fill a marketable buy of each size against the recorded book. A size the book could not fill is counted as a miss, not as a large number: unfillable and expensive are different findings.
