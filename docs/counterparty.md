# Who trades when the reference market is closed?

> **Short answer:** this report does not claim that weekend flow is more automated yet. The historical recorder captured regular hours and closures at different rates, so that comparison would be misleading. The recorder was corrected on 2026-09-05; one complete like-for-like session is still needed before the result is publishable.

**Why it matters:** Afterbell studies whether a tokenized equity keeps a healthy market when the underlying reference market is closed, and whether the trading pattern changes outside regular hours.

**What is reliable today:** the capture coverage, trade counts, and per-period measurements below. **What is not reliable yet:** a claim that one period has a more automated counterparty than another.

Computed from the trade records the recorder already stores. bStocks trade on a centralised order book, so this analysis uses the public trade tape rather than wallet tracking.

## How much of the tape we captured

Before 2026-09-05 14:43 UTC, the recorder fetched the last 50 trades once a minute; that historical limit caused the coverage bias described below. It now fetches up to 1000 trades per cycle. Trade ids are consecutive, so the size of anything missed is knowable exactly and is reported rather than assumed away.

| Symbol | Prints captured | Prints that occurred | Share of tape | Minutes fully captured | Quietest/busiest hour |
|---|---:|---:|---:|---:|---:|
| CRCLBUSDT | 267,883 | 424,647 | 63.1% | 86.8% | 0.129 |
| MUBUSDT | 108,581 | 125,016 | 86.9% | 96.8% | 0.103 |
| NVDABUSDT | 71,777 | 88,787 | 80.8% | 96.7% | 0.219 |
| SNDKBUSDT | 334,807 | 548,643 | 61.0% | 83.4% | 0.180 |
| TSLABUSDT | 64,962 | 77,044 | 84.3% | 97.2% | 0.055 |

In the historical pre-fix sample, the prints lost were the ones in bursts, which is exactly where automation would show. Timing figures below are therefore computed only across pairs of arrivals with consecutive ids, where nothing can have been missed between them.

The quietest/busiest-hour ratio is the quietest hour's volume divided by the busiest hour's volume across the whole day. A result of 1.0 means activity is evenly spread. It is measured per symbol, not per period, because the open session covers only 6.5 hours of the clock.

## Measurements by market period

| Symbol | Market period | Prints | Arrivals | Timed pairs | Inter-arrival CV | Bursts <200ms | Prints per arrival | Round sizes | Repeated sizes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CRCLBUSDT | Market holiday | 33,792 | 17,851 | 17,850 | 3.31 | 58.6% | 1.89 | 4.5% | 72.3% |
| CRCLBUSDT | Overnight closure | 27,344 | 18,686 | 18,497 | 2.64 | 55.5% | 1.46 | 5.0% | 75.5% |
| CRCLBUSDT | Weekend closure | 137,099 | 72,015 | 71,911 | 4.37 | 66.1% | 1.90 | 1.8% | 92.4% |
| CRCLBUSDT | Open | 28,637 | 15,153 | 14,764 | 2.41 | 52.1% | 1.89 | 4.0% | 70.7% |
| CRCLBUSDT | After close | 11,249 | 6,916 | 6,799 | 3.71 | 51.2% | 1.63 | 4.4% | 78.1% |
| CRCLBUSDT | Before open | 29,762 | 16,686 | 16,444 | 2.60 | 55.6% | 1.78 | 4.1% | 74.2% |
| MUBUSDT | Market holiday | 40,215 | 23,521 | 23,521 | 3.34 | 54.8% | 1.71 | 2.7% | 85.2% |
| MUBUSDT | Overnight closure | 12,487 | 8,168 | 8,144 | 2.82 | 37.5% | 1.53 | 1.3% | 75.6% |
| MUBUSDT | Weekend closure | 22,121 | 14,060 | 14,041 | 2.93 | 41.6% | 1.57 | 3.3% | 75.8% |
| MUBUSDT | Open | 18,431 | 13,023 | 12,871 | 2.30 | 41.5% | 1.42 | 3.2% | 75.5% |
| MUBUSDT | After close | 3,744 | 2,501 | 2,490 | 2.62 | 40.4% | 1.50 | 1.0% | 68.3% |
| MUBUSDT | Before open | 11,583 | 7,653 | 7,609 | 2.80 | 39.9% | 1.51 | 1.7% | 67.4% |
| NVDABUSDT | Market holiday | 12,708 | 8,449 | 8,449 | 3.06 | 36.5% | 1.50 | 3.0% | 74.2% |
| NVDABUSDT | Overnight closure | 9,435 | 5,570 | 5,537 | 1.95 | 14.2% | 1.69 | 1.5% | 71.9% |
| NVDABUSDT | Weekend closure | 15,962 | 11,420 | 11,394 | 2.18 | 19.1% | 1.40 | 3.6% | 74.4% |
| NVDABUSDT | Open | 12,445 | 8,303 | 8,231 | 2.11 | 26.1% | 1.50 | 1.8% | 70.1% |
| NVDABUSDT | After close | 8,671 | 5,257 | 5,187 | 2.90 | 34.2% | 1.65 | 0.9% | 84.5% |
| NVDABUSDT | Before open | 12,556 | 7,453 | 7,394 | 2.39 | 24.0% | 1.68 | 1.4% | 76.5% |
| SNDKBUSDT | Market holiday | 46,877 | 25,352 | 25,351 | 3.09 | 53.7% | 1.85 | 1.2% | 89.0% |
| SNDKBUSDT | Overnight closure | 42,352 | 25,844 | 25,673 | 2.84 | 53.0% | 1.64 | 0.5% | 87.0% |
| SNDKBUSDT | Weekend closure | 144,072 | 79,778 | 79,617 | 4.23 | 44.0% | 1.81 | 1.5% | 93.1% |
| SNDKBUSDT | Open | 37,775 | 25,726 | 25,084 | 2.51 | 52.1% | 1.47 | 1.0% | 83.1% |
| SNDKBUSDT | After close | 8,000 | 4,298 | 4,254 | 2.50 | 47.5% | 1.86 | 3.1% | 62.5% |
| SNDKBUSDT | Before open | 55,731 | 33,837 | 33,542 | 2.55 | 53.2% | 1.65 | 0.5% | 86.8% |
| TSLABUSDT | Market holiday | 6,580 | 4,745 | 4,745 | 2.44 | 17.1% | 1.39 | 5.0% | 67.8% |
| TSLABUSDT | Overnight closure | 7,743 | 5,708 | 5,688 | 2.31 | 26.2% | 1.36 | 2.8% | 65.7% |
| TSLABUSDT | Weekend closure | 18,171 | 10,142 | 10,127 | 2.13 | 16.7% | 1.79 | 4.5% | 80.8% |
| TSLABUSDT | Open | 16,792 | 10,944 | 10,820 | 2.08 | 33.6% | 1.53 | 2.2% | 69.0% |
| TSLABUSDT | After close | 4,527 | 2,691 | 2,675 | 2.39 | 28.3% | 1.68 | 2.8% | 68.4% |
| TSLABUSDT | Before open | 11,149 | 7,591 | 7,542 | 2.45 | 30.7% | 1.47 | 1.9% | 62.5% |

### What the numbers say

**Not enough of the tape was captured to answer the question, and the honest result is to say so rather than to publish a direction.**

The question worth testing was whether the counterparty on the other side of a weekend trade is more automated. Answering it means comparing two market periods, and that is only legitimate if both were sampled the same way. They were not: regular hours were captured at 24.3% and the weekend at 73.2%, because a historical fixed 50-print poll truncated a busy session far harder than a quiet weekend.

That difference is not a detail. Measured both ways, the answer reverses. Counting every consecutive-id pair over-samples busy minutes, whose prints are the ones that survive truncation, and makes regular hours look burstier than the weekend. Restricting to minutes captured without a hole over-samples quiet minutes instead, and makes the weekend look burstier than regular hours. Both estimators are biased, in opposite directions, and both bite hardest on the busiest state. A finding that flips depending on which of two flawed estimators is chosen is not a finding.

The cause was a recorder limit, not a market: it fetched only 50 prints per minute. That limit was raised to 1000 on 2026-09-05 at 14:43 UTC, and since then every cycle has been captured with no holes at all. Once a full session and a full closure have been recorded that way, this comparison becomes answerable and the answer will appear here.

The per-state tables below stand on their own — they describe what was seen, which is a fact — but no comparison **between** states should be read off them until coverage is even.


**Reading the columns.** An *arrival* is one aggressive order; the prints it produced against separate resting orders are collapsed into it, and `prints per arrival` reports how many makers it consumed. Inter-arrival CV near 1.0 is Poisson-ish arrival, the shape human order flow takes; below 1.0 is more regular than chance, above it is burstier. A dash means too few samples to say anything, which is reported rather than filled in.

Regenerate with `.venv/bin/python -m afterbell.counterparty`.
