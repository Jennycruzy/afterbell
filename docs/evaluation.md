| Metric | Value |
|---|---|
| Adversarial attacks run | 35 × 2 market states = 70 evaluations |
| Payloads that raised permitted size above control | **0** |
| Attacks that had to be refused, and were | 16/16 |
| Positive controls passed (the suite cannot win by refusing everything) | 6/6 |
| Live evaluations receipted | 2,460 |
| Regular-hours evaluations with a live reference | 393 |
| Of those, evaluations with a measurably normal book | 100 |
| Permitted in full on a normal book | 99/100 |
| **False-positive rate** (normal book, nothing measured out of band) | **1.00%** |
| Of which the designed closing-bell ramp | 1 |
| Correct reductions (a measurement really was out of band) | 109 |
| Refusals while a baseline was still uncalibrated | 0 |
| Refusals under a shut or stale reference market | 2,177 |
| Operator freeze refusals | 2 |
| Silent failures found by this project's own tooling and fixed | 6 |
| Order books recorded / reference prints measured | 17,965 / 14,135 |

**How the false-positive rate is defined.** The cohort is regular trading hours, with a live reference print, and a book that was measurably normal: spread at or under its own RTH median, depth at or over it, and the baseline past the sample minimum. Inside that cohort nothing the policy measures was out of band, so any withheld size is a false positive. Reductions where a measurement *was* out of band are counted separately as correct, and refusals during a closure are not counted at all, because the market really was shut.

The first version of this definition counted every regular-hours reduction as a false positive and reported 28.5%. That was wrong: most of those reductions were responses to a spread several times its own median, or to a baseline that had not yet reached its sample minimum. A guard that permitted those would be broken, not precise.

Regenerate with `python -m afterbell.evaluation`. Every figure above is computed from the adversarial corpus and the receipt ledger; none is maintained by hand.
