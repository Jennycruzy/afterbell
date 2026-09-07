## Counterparty composition of off-hours flow

Computed from the trade prints the recorder already stores. bStocks trade on a centralised order book, so on-chain wallet tracking cannot see this flow; nothing here uses it.

### What was actually captured

Before 2026-09-05 14:43 UTC, the recorder fetched the last 50 trades once a minute; that historical limit caused the coverage bias described below. It now fetches up to 1000 trades per cycle. Trade ids are consecutive, so the size of anything missed is knowable exactly, and is reported rather than assumed away.

| Symbol | Prints captured | Prints that occurred | Share of tape | Minutes with no hole | Diurnal flatness |
|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | 205,771 | 361,570 | 56.9% | 81.9% | 0.124 |
| MUBUSDT | 55,657 | 72,092 | 77.2% | 95.7% | 0.074 |
| NVDABUSDT | 53,178 | 70,188 | 75.8% | 95.5% | 0.181 |
| SNDKBUSDT | 230,511 | 443,619 | 52.0% | 77.2% | 0.193 |
| TSLABUSDT | 52,820 | 64,902 | 81.4% | 96.1% | 0.071 |

In the historical pre-fix sample, the prints lost were the ones in bursts, which is exactly where automation would show. Timing figures below are therefore computed only across pairs of arrivals with consecutive ids, where nothing can have been missed between them.

Diurnal flatness is the quietest hour's volume over the busiest hour's across the whole day, so 1.0 is a market that never sleeps. It is measured per symbol, not per state: a state cannot answer it, because `RTH_OPEN` spans 6.5 hours of the clock by definition.

### By market state

| Symbol | State | Prints | Arrivals | Timed pairs | Inter-arrival CV | Bursts <200ms | Prints per arrival | Round sizes | Repeated sizes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 22,067 | 16,480 | 16,291 | 2.78 | 57.7% | 1.34 | 4.2% | 76.2% |
| CRCLBUSDT | CLOSED_WEEKEND | 124,279 | 65,366 | 65,263 | 4.32 | 65.9% | 1.90 | 1.8% | 91.8% |
| CRCLBUSDT | RTH_OPEN | 28,037 | 14,897 | 14,508 | 2.39 | 51.5% | 1.88 | 4.0% | 70.6% |
| CRCLBUSDT | RTH_POST | 11,249 | 6,916 | 6,799 | 3.71 | 51.2% | 1.63 | 4.4% | 78.1% |
| CRCLBUSDT | RTH_PRE | 20,139 | 12,863 | 12,621 | 2.85 | 58.9% | 1.57 | 2.9% | 71.6% |
| MUBUSDT | CLOSED_OVERNIGHT | 6,352 | 4,227 | 4,203 | 2.50 | 42.4% | 1.50 | 1.1% | 71.8% |
| MUBUSDT | CLOSED_WEEKEND | 20,797 | 13,170 | 13,151 | 2.94 | 41.6% | 1.58 | 3.4% | 75.6% |
| MUBUSDT | RTH_OPEN | 18,019 | 12,792 | 12,640 | 2.27 | 40.8% | 1.41 | 3.2% | 76.1% |
| MUBUSDT | RTH_POST | 3,744 | 2,501 | 2,490 | 2.62 | 40.4% | 1.50 | 1.0% | 68.3% |
| MUBUSDT | RTH_PRE | 6,745 | 4,716 | 4,672 | 2.97 | 37.3% | 1.43 | 1.2% | 66.1% |
| NVDABUSDT | CLOSED_OVERNIGHT | 8,018 | 4,750 | 4,717 | 2.00 | 13.1% | 1.69 | 1.2% | 72.2% |
| NVDABUSDT | CLOSED_WEEKEND | 15,431 | 11,025 | 10,999 | 2.18 | 18.7% | 1.40 | 3.5% | 74.2% |
| NVDABUSDT | RTH_OPEN | 12,174 | 8,115 | 8,043 | 2.08 | 25.1% | 1.50 | 1.8% | 69.9% |
| NVDABUSDT | RTH_POST | 8,671 | 5,257 | 5,187 | 2.90 | 34.2% | 1.65 | 0.9% | 84.5% |
| NVDABUSDT | RTH_PRE | 8,884 | 5,437 | 5,378 | 2.52 | 21.6% | 1.63 | 1.5% | 74.6% |
| SNDKBUSDT | CLOSED_OVERNIGHT | 21,322 | 12,759 | 12,588 | 2.46 | 48.3% | 1.67 | 0.4% | 81.4% |
| SNDKBUSDT | CLOSED_WEEKEND | 140,985 | 77,969 | 77,808 | 4.31 | 43.8% | 1.81 | 1.4% | 93.1% |
| SNDKBUSDT | RTH_OPEN | 36,805 | 25,307 | 24,665 | 2.49 | 51.5% | 1.45 | 1.0% | 83.8% |
| SNDKBUSDT | RTH_POST | 8,000 | 4,298 | 4,254 | 2.50 | 47.5% | 1.86 | 3.1% | 62.5% |
| SNDKBUSDT | RTH_PRE | 23,399 | 14,785 | 14,491 | 2.43 | 47.7% | 1.58 | 0.4% | 82.8% |
| TSLABUSDT | CLOSED_OVERNIGHT | 6,629 | 4,993 | 4,973 | 2.46 | 27.4% | 1.33 | 2.4% | 65.2% |
| TSLABUSDT | CLOSED_WEEKEND | 17,878 | 9,978 | 9,963 | 2.12 | 16.8% | 1.79 | 4.4% | 80.9% |
| TSLABUSDT | RTH_OPEN | 16,297 | 10,640 | 10,516 | 2.05 | 32.0% | 1.53 | 2.2% | 69.3% |
| TSLABUSDT | RTH_POST | 4,527 | 2,691 | 2,675 | 2.39 | 28.3% | 1.68 | 2.8% | 68.4% |
| TSLABUSDT | RTH_PRE | 7,489 | 5,259 | 5,210 | 2.57 | 28.8% | 1.42 | 1.7% | 61.3% |

### What the numbers say

**Not enough of the tape was captured to answer the question, and the honest result is to say so rather than to publish a direction.**

The hypothesis worth testing was that the counterparty on the other side of a weekend trade is another agent. Answering it means comparing two market states, and that is only legitimate if both were sampled the same way. They were not: regular hours were captured at 24.0% and the weekend at 72.3%, because a historical fixed 50-print poll truncated a busy session far harder than a quiet weekend.

That difference is not a detail. Measured both ways, the answer reverses. Counting every consecutive-id pair over-samples busy minutes, whose prints are the ones that survive truncation, and makes regular hours look burstier than the weekend. Restricting to minutes captured without a hole over-samples quiet minutes instead, and makes the weekend look burstier than regular hours. Both estimators are biased, in opposite directions, and both bite hardest on the busiest state. A finding that flips depending on which of two flawed estimators is chosen is not a finding.

The cause was a recorder limit, not a market: `TRADE_LIMIT` was 50 prints per minute, which is written up as the sixth silent failure. It was raised to 1000 on 2026-09-05 at 14:43 UTC, and since then every cycle has been captured with no holes at all. Once a full session and a full closure have been recorded that way, this comparison becomes answerable and the answer will appear here.

The per-state tables below stand on their own — they describe what was seen, which is a fact — but no comparison **between** states should be read off them until coverage is even.


**Reading the columns.** An *arrival* is one aggressive order; the prints it produced against separate resting orders are collapsed into it, and `prints per arrival` reports how many makers it consumed. Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human order flow takes; below 1.0 is more regular than chance, above it is burstier. A dash means too few samples to say anything, which is reported rather than filled in.

Regenerate with `.venv/bin/python -m afterbell.counterparty`.
