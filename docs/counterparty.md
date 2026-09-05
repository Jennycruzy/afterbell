## Counterparty composition of off-hours flow

Computed from the trade prints the recorder already stores. bStocks trade on a centralised order book, so on-chain wallet tracking cannot see this flow; nothing here uses it.

### What was actually captured

The recorder fetches the last 50 trades once a minute. Trade ids are consecutive, so the size of anything missed is knowable exactly, and is reported rather than assumed away.

| Symbol | Prints captured | Prints that occurred | Share of tape | Minutes with no hole | Diurnal flatness |
|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | 93,422 | 207,389 | 45.0% | 72.1% | 0.138 |
| MUBUSDT | 40,208 | 56,643 | 71.0% | 93.2% | 0.055 |
| NVDABUSDT | 43,801 | 60,811 | 72.0% | 92.9% | 0.147 |
| SNDKBUSDT | 108,530 | 321,638 | 33.7% | 64.2% | 0.095 |
| TSLABUSDT | 42,766 | 54,848 | 78.0% | 93.9% | 0.066 |

The prints lost are the ones in bursts, which is exactly where automation would show. Timing figures below are therefore computed only across pairs of arrivals with consecutive ids, where nothing can have been missed between them.

Diurnal flatness is the quietest hour's volume over the busiest hour's across the whole day, so 1.0 is a market that never sleeps. It is measured per symbol, not per state: a state cannot answer it, because `RTH_OPEN` spans 6.5 hours of the clock by definition.

### By market state

| Symbol | State | Prints | Arrivals | Timed pairs | Inter-arrival CV | Bursts <200ms | Prints per arrival | Round sizes | Repeated sizes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CRCLBUSDT | CLOSED_OVERNIGHT | 22,067 | 16,480 | 16,291 | 2.78 | 57.7% | 1.34 | 4.2% | 76.2% |
| CRCLBUSDT | CLOSED_WEEKEND | 11,930 | 8,351 | 8,270 | 3.28 | 50.0% | 1.43 | 3.7% | 82.0% |
| CRCLBUSDT | RTH_OPEN | 28,037 | 14,897 | 14,508 | 2.39 | 51.5% | 1.88 | 4.0% | 70.6% |
| CRCLBUSDT | RTH_POST | 11,249 | 6,916 | 6,799 | 3.71 | 51.2% | 1.63 | 4.4% | 78.1% |
| CRCLBUSDT | RTH_PRE | 20,139 | 12,863 | 12,621 | 2.85 | 58.9% | 1.57 | 2.9% | 71.6% |
| MUBUSDT | CLOSED_OVERNIGHT | 6,352 | 4,227 | 4,203 | 2.50 | 42.4% | 1.50 | 1.1% | 71.8% |
| MUBUSDT | CLOSED_WEEKEND | 5,348 | 3,572 | 3,553 | 2.68 | 37.6% | 1.50 | 4.0% | 69.9% |
| MUBUSDT | RTH_OPEN | 18,019 | 12,792 | 12,640 | 2.27 | 40.8% | 1.41 | 3.2% | 76.1% |
| MUBUSDT | RTH_POST | 3,744 | 2,501 | 2,490 | 2.62 | 40.4% | 1.50 | 1.0% | 68.3% |
| MUBUSDT | RTH_PRE | 6,745 | 4,716 | 4,672 | 2.97 | 37.3% | 1.43 | 1.2% | 66.1% |
| NVDABUSDT | CLOSED_OVERNIGHT | 8,018 | 4,750 | 4,717 | 2.00 | 13.1% | 1.69 | 1.2% | 72.2% |
| NVDABUSDT | CLOSED_WEEKEND | 6,054 | 4,312 | 4,286 | 2.43 | 26.4% | 1.40 | 3.5% | 65.3% |
| NVDABUSDT | RTH_OPEN | 12,174 | 8,115 | 8,043 | 2.08 | 25.1% | 1.50 | 1.8% | 69.9% |
| NVDABUSDT | RTH_POST | 8,671 | 5,257 | 5,187 | 2.90 | 34.2% | 1.65 | 0.9% | 84.5% |
| NVDABUSDT | RTH_PRE | 8,884 | 5,437 | 5,378 | 2.52 | 21.6% | 1.63 | 1.5% | 74.6% |
| SNDKBUSDT | CLOSED_OVERNIGHT | 21,322 | 12,759 | 12,588 | 2.46 | 48.3% | 1.67 | 0.4% | 81.4% |
| SNDKBUSDT | CLOSED_WEEKEND | 19,004 | 10,224 | 10,063 | 3.06 | 42.5% | 1.86 | 3.1% | 80.2% |
| SNDKBUSDT | RTH_OPEN | 36,805 | 25,307 | 24,665 | 2.49 | 51.5% | 1.45 | 1.0% | 83.8% |
| SNDKBUSDT | RTH_POST | 8,000 | 4,298 | 4,254 | 2.50 | 47.5% | 1.86 | 3.1% | 62.5% |
| SNDKBUSDT | RTH_PRE | 23,399 | 14,785 | 14,491 | 2.43 | 47.7% | 1.58 | 0.4% | 82.8% |
| TSLABUSDT | CLOSED_OVERNIGHT | 6,629 | 4,993 | 4,973 | 2.46 | 27.4% | 1.33 | 2.4% | 65.2% |
| TSLABUSDT | CLOSED_WEEKEND | 7,824 | 4,141 | 4,126 | 1.85 | 20.1% | 1.89 | 3.6% | 76.9% |
| TSLABUSDT | RTH_OPEN | 16,297 | 10,640 | 10,516 | 2.05 | 32.0% | 1.53 | 2.2% | 69.3% |
| TSLABUSDT | RTH_POST | 4,527 | 2,691 | 2,675 | 2.39 | 28.3% | 1.68 | 2.8% | 68.4% |
| TSLABUSDT | RTH_PRE | 7,489 | 5,259 | 5,210 | 2.57 | 28.8% | 1.42 | 1.7% | 61.3% |

### What the numbers say

The hypothesis worth testing was that the counterparty on the other side of a weekend trade is another agent. **The measurements do not support it.**

Weekend arrivals are less clustered than regular-hours ones — 35.3% of weekend arrivals land within 200ms of the previous one against 40.2% during regular trading — and round-number trade sizes go **up** off-hours, not down: 2.43% during regular hours against 3.58% on the weekend, higher in 4 of the 5 symbols.

Round sizes are the signature of somebody typing a number. A market maker quoting continuously does not deal in hundreds. So the weekend counterparty looks *less* automated than the weekday one, not more.

That is a finding against the hypothesis, and it makes the case for a guard stronger rather than weaker. The risk of trading a tokenized equity while its reference market is shut was never that a sophisticated counterparty would pick you off. It is that the price has no discovery venue behind it for 71 hours, and the people still trading it are the least equipped to notice.


**Reading the columns.** An *arrival* is one aggressive order; the prints it produced against separate resting orders are collapsed into it, and `prints per arrival` reports how many makers it consumed. Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human order flow takes; below 1.0 is more regular than chance, above it is burstier. A dash means too few samples to say anything, which is reported rather than filled in.

Regenerate with `python -m afterbell.counterparty`.
