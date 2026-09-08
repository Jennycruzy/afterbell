## Counterparty composition of off-hours flow

Computed from the trade prints the recorder already stores. bStocks trade on a centralised order book, so on-chain wallet tracking cannot see this flow; nothing here uses it.

### What was actually captured

Before 2026-09-05 14:43 UTC, the recorder fetched the last 50 trades once a minute; that historical limit caused the coverage bias described below. It now fetches up to 1000 trades per cycle. Trade ids are consecutive, so the size of anything missed is knowable exactly, and is reported rather than assumed away.

| Symbol | Prints captured | Prints that occurred | Share of tape | Minutes with no hole | Diurnal flatness |
|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | 259,183 | 415,947 | 62.3% | 86.3% | 0.154 |
| MUBUSDT | 104,950 | 121,385 | 86.5% | 96.7% | 0.149 |
| NVDABUSDT | 68,335 | 85,345 | 80.1% | 96.6% | 0.240 |
| SNDKBUSDT | 312,294 | 525,975 | 59.4% | 82.8% | 0.184 |
| TSLABUSDT | 61,500 | 73,582 | 83.6% | 97.1% | 0.078 |

In the historical pre-fix sample, the prints lost were the ones in bursts, which is exactly where automation would show. Timing figures below are therefore computed only across pairs of arrivals with consecutive ids, where nothing can have been missed between them.

Diurnal flatness is the quietest hour's volume over the busiest hour's across the whole day, so 1.0 is a market that never sleeps. It is measured per symbol, not per state: a state cannot answer it, because `RTH_OPEN` spans 6.5 hours of the clock by definition.

### By market state

| Symbol | State | Prints | Arrivals | Timed pairs | Inter-arrival CV | Bursts <200ms | Prints per arrival | Round sizes | Repeated sizes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_HOLIDAY | 33,792 | 17,851 | 17,850 | 3.31 | 58.6% | 1.89 | 4.5% | 72.3% |
| CRCLBUSDT | CLOSED_OVERNIGHT | 27,344 | 18,686 | 18,497 | 2.64 | 55.5% | 1.46 | 5.0% | 75.5% |
| CRCLBUSDT | CLOSED_WEEKEND | 137,099 | 72,015 | 71,911 | 4.37 | 66.1% | 1.90 | 1.8% | 92.4% |
| CRCLBUSDT | RTH_OPEN | 28,037 | 14,897 | 14,508 | 2.39 | 51.5% | 1.88 | 4.0% | 70.6% |
| CRCLBUSDT | RTH_POST | 11,249 | 6,916 | 6,799 | 3.71 | 51.2% | 1.63 | 4.4% | 78.1% |
| CRCLBUSDT | RTH_PRE | 21,662 | 13,509 | 13,267 | 2.74 | 57.8% | 1.60 | 3.0% | 71.9% |
| MUBUSDT | CLOSED_HOLIDAY | 40,215 | 23,521 | 23,521 | 3.34 | 54.8% | 1.71 | 2.7% | 85.2% |
| MUBUSDT | CLOSED_OVERNIGHT | 12,487 | 8,168 | 8,144 | 2.82 | 37.5% | 1.53 | 1.3% | 75.6% |
| MUBUSDT | CLOSED_WEEKEND | 22,121 | 14,060 | 14,041 | 2.93 | 41.6% | 1.57 | 3.3% | 75.8% |
| MUBUSDT | RTH_OPEN | 18,019 | 12,792 | 12,640 | 2.27 | 40.8% | 1.41 | 3.2% | 76.1% |
| MUBUSDT | RTH_POST | 3,744 | 2,501 | 2,490 | 2.62 | 40.4% | 1.50 | 1.0% | 68.3% |
| MUBUSDT | RTH_PRE | 8,364 | 5,674 | 5,630 | 3.03 | 39.6% | 1.47 | 1.4% | 67.0% |
| NVDABUSDT | CLOSED_HOLIDAY | 12,708 | 8,449 | 8,449 | 3.06 | 36.5% | 1.50 | 3.0% | 74.2% |
| NVDABUSDT | CLOSED_OVERNIGHT | 9,435 | 5,570 | 5,537 | 1.95 | 14.2% | 1.69 | 1.5% | 71.9% |
| NVDABUSDT | CLOSED_WEEKEND | 15,962 | 11,420 | 11,394 | 2.18 | 19.1% | 1.40 | 3.6% | 74.4% |
| NVDABUSDT | RTH_OPEN | 12,174 | 8,115 | 8,043 | 2.08 | 25.1% | 1.50 | 1.8% | 69.9% |
| NVDABUSDT | RTH_POST | 8,671 | 5,257 | 5,187 | 2.90 | 34.2% | 1.65 | 0.9% | 84.5% |
| NVDABUSDT | RTH_PRE | 9,385 | 5,778 | 5,719 | 2.46 | 22.1% | 1.62 | 1.5% | 74.8% |
| SNDKBUSDT | CLOSED_HOLIDAY | 46,877 | 25,352 | 25,351 | 3.09 | 53.7% | 1.85 | 1.2% | 89.0% |
| SNDKBUSDT | CLOSED_OVERNIGHT | 42,352 | 25,844 | 25,673 | 2.84 | 53.0% | 1.64 | 0.5% | 87.0% |
| SNDKBUSDT | CLOSED_WEEKEND | 144,072 | 79,778 | 79,617 | 4.23 | 44.0% | 1.81 | 1.5% | 93.1% |
| SNDKBUSDT | RTH_OPEN | 36,805 | 25,307 | 24,665 | 2.49 | 51.5% | 1.45 | 1.0% | 83.8% |
| SNDKBUSDT | RTH_POST | 8,000 | 4,298 | 4,254 | 2.50 | 47.5% | 1.86 | 3.1% | 62.5% |
| SNDKBUSDT | RTH_PRE | 34,188 | 21,247 | 20,953 | 2.67 | 52.2% | 1.61 | 0.5% | 84.7% |
| TSLABUSDT | CLOSED_HOLIDAY | 6,580 | 4,745 | 4,745 | 2.44 | 17.1% | 1.39 | 5.0% | 67.8% |
| TSLABUSDT | CLOSED_OVERNIGHT | 7,743 | 5,708 | 5,688 | 2.31 | 26.2% | 1.36 | 2.8% | 65.7% |
| TSLABUSDT | CLOSED_WEEKEND | 18,171 | 10,142 | 10,127 | 2.13 | 16.7% | 1.79 | 4.5% | 80.8% |
| TSLABUSDT | RTH_OPEN | 16,297 | 10,640 | 10,516 | 2.05 | 32.0% | 1.53 | 2.2% | 69.3% |
| TSLABUSDT | RTH_POST | 4,527 | 2,691 | 2,675 | 2.39 | 28.3% | 1.68 | 2.8% | 68.4% |
| TSLABUSDT | RTH_PRE | 8,182 | 5,658 | 5,609 | 2.50 | 29.4% | 1.45 | 1.6% | 61.0% |

### What the numbers say

**Not enough of the tape was captured to answer the question, and the honest result is to say so rather than to publish a direction.**

The hypothesis worth testing was that the counterparty on the other side of a weekend trade is another agent. Answering it means comparing two market states, and that is only legitimate if both were sampled the same way. They were not: regular hours were captured at 24.0% and the weekend at 73.2%, because a historical fixed 50-print poll truncated a busy session far harder than a quiet weekend.

That difference is not a detail. Measured both ways, the answer reverses. Counting every consecutive-id pair over-samples busy minutes, whose prints are the ones that survive truncation, and makes regular hours look burstier than the weekend. Restricting to minutes captured without a hole over-samples quiet minutes instead, and makes the weekend look burstier than regular hours. Both estimators are biased, in opposite directions, and both bite hardest on the busiest state. A finding that flips depending on which of two flawed estimators is chosen is not a finding.

The cause was a recorder limit, not a market: `TRADE_LIMIT` was 50 prints per minute, which is written up as the sixth silent failure. It was raised to 1000 on 2026-09-05 at 14:43 UTC, and since then every cycle has been captured with no holes at all. Once a full session and a full closure have been recorded that way, this comparison becomes answerable and the answer will appear here.

The per-state tables below stand on their own — they describe what was seen, which is a fact — but no comparison **between** states should be read off them until coverage is even.


**Reading the columns.** An *arrival* is one aggressive order; the prints it produced against separate resting orders are collapsed into it, and `prints per arrival` reports how many makers it consumed. Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human order flow takes; below 1.0 is more regular than chance, above it is burstier. A dash means too few samples to say anything, which is reported rather than filled in.

Regenerate with `.venv/bin/python -m afterbell.counterparty`.
