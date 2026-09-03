#!/usr/bin/env python
"""Rehearse a market-state transition before it happens for real.

Beat 1 of the demo is filmed at Friday's closing bell. It happens once, it
cannot be re-shot, and the thing being filmed - `RTH_OPEN` flipping to
`CLOSED_WEEKEND` while `REFERENCE_AGE` starts counting from zero - lasts one
second. Discovering a formatting bug or an off-by-one boundary at 19:59:59 on
Friday is discovering it too late.

So the clock is stepped through the bell in advance, against the live order
book, and every frame is printed exactly as it will be rendered on the night.

HONESTY: `--at` moves the CLOCK ONLY. The order book, the pair status and the
reference price are whatever the market says at the moment this runs, because
there is no truthful way to fetch a live book as it stood at another instant.
Each frame is labelled with both times. Nothing in the production path can pass
a simulated time; this script is the only caller that does.

    python scripts/rehearse.py                      # Friday's bell
    python scripts/rehearse.py --date 2026-09-08 --from 13:25 --to 13:35
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from afterbell.clock import (
    MarketState, evaluate as clock_at, format_age, last_rth_close,
)
from afterbell.engine import Guard
from afterbell.guard import OrderRequest
from afterbell.measure import Side
from afterbell.policy import load as load_policy

# Friday 4 Sep 2026, 20:00:00 UTC. The one moment that cannot be rescheduled.
BELL = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", default=BELL.date().isoformat())
    ap.add_argument("--from", dest="start", default="19:55",
                    help="UTC HH:MM to start (default 19:55)")
    ap.add_argument("--to", dest="end", default="20:05",
                    help="UTC HH:MM to stop (default 20:05)")
    ap.add_argument("--step", type=int, default=60, help="seconds per frame")
    ap.add_argument("--symbol", default="NVDABUSDT")
    ap.add_argument("--notional", type=float, default=5000.0)
    ap.add_argument("--query", default="buy Nvidia")
    ap.add_argument("--policy", default=None)
    ap.add_argument("--receipts", action="store_true",
                    help="write receipts to the real ledger (default: do not)")
    ap.add_argument("--live-reference", action="store_true",
                    help="use the real reference timestamp instead of the "
                         "one the simulated clock implies")
    a = ap.parse_args()

    d = date.fromisoformat(a.date)
    start = datetime.combine(d, _parse_hhmm(a.start), tzinfo=timezone.utc)
    end = datetime.combine(d, _parse_hhmm(a.end), tzinfo=timezone.utc)
    if end <= start:
        ap.error("--to must be after --from")

    pol = load_policy(a.policy)
    # A rehearsal must not pollute the hash chain the submission publishes, so
    # receipts go to a scratch ledger unless explicitly asked otherwise.
    ledger = (None if a.receipts else
              Path(__file__).resolve().parent.parent / "data" / "rehearsal.jsonl")
    guard = Guard(pol, ledger_path=ledger) if ledger else Guard(pol)

    req = OrderRequest(a.symbol, Side(("BUY")), a.notional, query=a.query)
    real_now = datetime.now(timezone.utc)

    print()
    print("  REHEARSAL - the clock is simulated, the order book is live")
    print(f"  simulated {start:%a %d %b %H:%M}Z -> {end:%H:%M}Z "
          f"every {a.step}s")
    print(f"  live book fetched at {real_now:%a %d %b %H:%M:%S}Z")
    print(f"  reference price live; timestamp "
          f"{'live too' if a.live_reference else 'from the simulated calendar'}")
    print(f"  receipts -> {'the real ledger' if a.receipts else 'data/rehearsal.jsonl'}")
    print()
    print(f"  {'simulated':>9}  {'state':<17} {'REFERENCE_AGE':>13}  "
          f"{'verdict':<7} {'permitted':>10}  binding")
    print(f"  {'-'*9}  {'-'*17} {'-'*13}  {'-'*7} {'-'*10}  {'-'*18}")

    prev_state = None
    t = start
    while t <= end:
        ctx = guard.build_context(req, at=t)
        if not a.live_reference and ctx.reference_price is not None:
            # The live fetch returns a reference stamped at the most recent
            # REAL session, so a simulated Friday would show a REFERENCE_AGE
            # of two days and the one column Beat 1 is about would go
            # unrehearsed. Keep the live PRICE - it is a real number - and
            # move only the timestamp to the one the simulated calendar
            # implies: the tape while a session is running, the last closing
            # bell once it is not. This is the same rule reference.py applies;
            # it is applied here to a simulated instant.
            ctx.reference_ts = (
                t if clock_at(t).state is MarketState.RTH_OPEN
                else last_rth_close(t))
        d_ = guard.evaluate(req, ctx)
        age = ("no reference" if ctx.reference_age_s is None
               else format_age(ctx.reference_age_s))
        state = ctx.clock.state.value
        flip = ""
        if prev_state is not None and state != prev_state:
            flip = f"   <<< {prev_state} -> {state}"
        print(f"  {t:%H:%M:%S}  {state:<17} {age:>13}  "
              f"{d_.verdict.value:<7} {d_.allowed_notional:>10,.0f}  "
              f"{d_.binding_constraint}{flip}")
        prev_state = state
        t += timedelta(seconds=a.step)

    print()
    transitions = clock_at(end).state.value
    print(f"  ended in {transitions}. Re-run with --step 1 around the bell to "
          f"check the boundary second.")
    print()


if __name__ == "__main__":
    main()
