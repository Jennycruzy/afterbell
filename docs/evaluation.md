| Metric | Value |
|---|---|
| Adversarial attacks run | 35 × 2 market states = 70 evaluations |
| Payloads that raised permitted size above control | **0** |
| Attacks that had to be refused, and were | 16/16 |
| Positive controls passed (the suite cannot win by refusing everything) | 6/6 |
| Live evaluations receipted | 6,712 |
| Regular-hours evaluations with a live reference | 399 |
| Of those, evaluations with a measurably normal book | 103 |
| Permitted in full on a normal book | 99/103 |
| **False-positive rate** (normal book, nothing measured out of band) | **3.88%** |
| Of which the designed closing-bell ramp | 1 |
| Correct reductions (a measurement really was out of band) | 112 |
| Refusals before data coverage was complete | 0 |
| Refusals under a shut or stale reference market | 6,426 |
| Operator freeze refusals | 2 |
| Recorder and measurement issues found by this project's own tooling and fixed | 6 |
| Order books recorded / reference prints measured | 39,365 / 35,520 |

**How the false-positive rate is defined.** The cohort is regular trading hours, with a live reference print, and a book that was measurably normal: spread at or under its own regular-hours median, depth at or over it, and the normal-hours comparison has enough observations. Inside that cohort nothing the policy measures was out of band, so any withheld size is a false positive. Reductions where a measurement *was* out of band are counted separately as correct, and refusals during a closure are not counted at all, because the market really was shut.

**What the cohort is made of.** The continuous monitor requests a constant `base_notional` — 5,000 USDT — once a minute, so this is one repeated probe rather than a realistic mix of order sizes. That makes the rate stricter, not looser: asking for exactly the base notional is the largest request that can still be permitted in full, so any factor below 1.0 shows up as a reduction. A smaller order would pass more easily. The rate should be read as "asked for the full base size under normal conditions, it was permitted in full", not as a claim about arbitrary order flow.

The first version of this definition counted every regular-hours reduction as a false positive and reported 28.5%. That was wrong: most of those reductions were responses to a spread several times its own median, or to a normal-hours comparison that did not yet have enough observations. A safety layer that permitted those would be broken, not precise.

Regenerate with `.venv/bin/python -m afterbell.evaluation`. Every figure above is computed from the adversarial corpus and the receipt ledger; none is maintained by hand.
