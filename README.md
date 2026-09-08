# AFTERBELL

> **The stock sleeps. The token doesn't.**

**AFTERBELL is an autonomous safety agent for AI agents trading Binance bStocks
through Agent OS.** It watches the always-open token market against the hours
and condition of the U.S. stock market underneath it, notices material safety
changes without being asked, and gives a trading agent the largest defensible
order size before anything reaches execution.

The AI agent owns the trade intent. AFTERBELL independently owns the safety
limit. Binance Agent OS owns authenticated execution.

AFTERBELL does not predict prices, choose investments, or hold an exchange
credential. Its financial decisions are deterministic by design: a language
model may explain a result, but it cannot choose a price, threshold, amount, or
outcome, and it cannot overturn a refusal. Through its own governed handoff,
unsafe size is impossible to approve by accident.

Built for the **Binance Agent OS Mini Hackathon, Track A**.

| | |
|---|---|
| **Live dashboard** | <https://afterbell.site> — running now, updates every minute |
| **Public MCP endpoint** | `https://afterbell.site/mcp` — three read-only tools, no key needed |
| **How it fits together** | [Architecture](#architecture) |
| **Connect an agent** | [Connect your AI agent](#connect-your-ai-agent) |
| **Measured baselines** | [`docs/calibration.md`](docs/calibration.md) |
| **Safety-test results** | [`docs/evaluation.md`](docs/evaluation.md) |
| **The one real order** | [`docs/live-acceptance.md`](docs/live-acceptance.md) |

## Architecture

AFTERBELL is the autonomous safety agent inside an Agent OS trading workflow.
Any compatible AI trading agent can use its MCP tools before it acts. Two
agents and one exchange, each owning exactly one thing:

```text
                    ┌─────────────────────────────────────┐
                    │      any AI trading agent           │
                    │  owns the intent: what to trade     │
                    └──────┬───────────────────────┬──────┘
                           │ 1. propose a trade    │
                           ▼                       │
        ┌──────────────────────────────────┐       │
        │   AFTERBELL — safety agent       │       │
        │   owns the limit · holds no key  │       │
        ├──────────────────────────────────┤       │
        │  get_safety_posture              │       │
        │  get_market_state                │       │
        │  evaluate_order                  │       │
        └──────────────┬───────────────────┘       │
                       │ 2. current posture,       │
                       │    permitted size,        │
                       │    the reason,            │
                       │    a decision receipt     │
                       ▼                           │
             the agent keeps to that ceiling       │
                       │                           │
                       │ 3. submit within it       │
                       ▼                           ▼
        ┌──────────────────────────────────────────────────┐
        │                 Binance Agent OS                 │
        │        owns execution · holds the credential     │
        └──────────────────────────────────────────────────┘

    Separately, when execution is enabled, AFTERBELL issues a signed
    authorization bound to one specific proposal, which a supported
    client redeems. That is the governed handoff below, not a value
    these read-only tools return.
```

The agent owns intent. AFTERBELL owns the deterministic limit. Agent OS owns
authenticated execution. No party does another's job, and the limit is decided
by ordinary code rather than by a model.

Inside AFTERBELL, one request travels a straight line:

```text
recorded token books + reference prices + exchange calendar
                              │
                              ▼
             deterministic measurements and instrument checks
                              │
                              ▼
             smallest safe amount + plain-language explanation
                              │
                              ▼
                 recorded decision + order limit
                              │
                              ▼
                   hash-linked receipt ledger
```

The recorder runs separately from the dashboard and holds no credential. The
dashboard shows the current order limit and cannot place an order.

## Connect your AI agent

AFTERBELL is a peer on the protocol, not an adapter for one product. Any
MCP-capable agent can use it — there is no SDK, no plugin, and no client this
side requires. Pair it with Binance Agent OS in the same client, ask AFTERBELL
what size is defensible, and restrict the Agent OS order to the ceiling that
comes back. Whatever a client needs in order to talk to Binance is Binance's
requirement, not AFTERBELL's; nothing here narrows which agent you bring. That last step is the agent's to honour: AFTERBELL
governs its own handoff, not somebody else's credential.

The endpoint carries no account credential and has no execution capability. A
caller can read state, or create a rate-limited safety evaluation which is
receipted like any other; it cannot place an order. That is why it can be
public:

```bash
curl -sS https://afterbell.site/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"evaluate_order",
                 "arguments":{"symbol":"NVDABUSDT","side":"BUY",
                              "notional":5000,"query":"buy 5000 of Nvidia"}}}'
```

That is a plain HTTP client with no SDK, which is the point: nothing about the
surface is specific to one agent framework.

**Example, using the Codex CLI as one supported client:**

```bash
codex mcp add afterbell --url https://afterbell.site/mcp
```

The two servers then sit side by side in the same client, which is the
architecture above with nothing else added:

```text
Name              Url                                    Status   Auth
afterbell         https://afterbell.site/mcp             enabled  Unsupported
binance-agent-os  https://agent.binance.com/mcp/agentic  enabled  OAuth
```

`Unsupported` in the auth column is `auth_status`: it describes the sign-in a
server offers, not a problem. AFTERBELL offers none, because it has nothing to
protect. The credential lives on the other row, with the party whose job is
execution.

Codex is one client, not a dependency, and it is worth being exact about what
has been demonstrated with it. Codex discovers this server and resolves its
tools. Codex is also the client that placed the one recorded live order — but
it did that through Binance Agent OS, submitting a signed authorization this
package had already issued, which is a different path from calling the tools
above. Note that `codex exec` refuses MCP calls non-interactively with
`MCP tool call requires approval, but approval policy is never`; that is the
client's own gate, unrelated to this server.

### What the agent actually sees

Taken from the live endpoint on 8 September 2026 at 16:48 UTC. First the agent
asks what has changed while it was not looking:

```text
get_safety_posture

  market_state      RTH_OPEN          liquidity        normal
  reference         fresh             price_agreement  NOMINAL
  venue_status      trading           account_evidence missing
  verdict           BLOCK
  authorizes        null
```

Then it proposes the trade it wants:

```text
evaluate_order  NVDABUSDT  BUY  5000 USDT  "buy 5000 of Nvidia"

  verdict          BLOCK
  requested        5000.0
  permitted        0.0
  binding check    Account exposure
  reference age    00:00:01
  receipt          #6912

  Market timing        PASS      Instrument identity  PASS
  Liquidity            PASS      Contract address     PASS
  Price agreement      PASS      Account exposure     BLOCK
  Corporate actions    WARN
```

Six checks are healthy and the seventh is not, so the answer is zero. A
well-behaved agent stops there. The refusal is receipted in the same
hash-linked ledger as every other decision, so what it was told is on the
record whether or not it listened.

A separate recorded execution used the signed-authorization handoff rather than
these tools: 5.00 USDT requested, 5.00 permitted, 4.86192 actually spent, venue
order `54422149`, redeemed by `codex-binance-agent-os` and recorded in
[`docs/live-acceptance.md`](docs/live-acceptance.md). The two are complementary
proofs — that any compatible agent can query this server, and that the
authorization path has produced a real fill — not one continuous demonstration.

## The problem

A tokenized share can trade 24 hours a day. The U.S. stock it references cannot:
it trades during regular weekday sessions and then stops updating. A token can
therefore keep moving for a weekend or holiday while the most recent independent
stock price becomes older and older.

A normal order-size check misses that time gap. AFTERBELL treats it as a first-
class risk input:

> **The longer the reference market has been quiet, the less new exposure the
> system is willing to approve.**

The same idea also applies when the token book becomes thin, the token and
reference price disagree, the instrument cannot be identified exactly, or the
current account position is unknown.

## What happens when a request arrives

1. The request is resolved to one of the five supported token pairs.
2. AFTERBELL reads the recorded token book, the last regular-hours reference
   price, the market calendar, and the instrument registry.
3. It checks timing, liquidity, price agreement, corporate-action status,
   instrument identity, contract address, and current account exposure.
4. It returns a clear result and an amount no larger than the request: clear,
   caution, smaller size, or blocked.
5. It writes a tamper-evident receipt containing the measurements and the exact
   safety-settings fingerprint used for that decision.

Every number comes from ordinary deterministic code. A language model can
explain a result, but it cannot choose a price, threshold, amount, or outcome.

## What it does when nobody asks

The monitor runs unattended, and most of the time it has nothing to say. It
reduces each cycle to the bands the limits already respond to: where the
reference market is in its calendar, how stale the independent price has
become, how the book compares with its own regular-hours normal, how far the
token has drifted from the reference, what the venue reports, and whether there
is current account evidence.

When one of those bands moves, it records the change on its own and says why it
matters:

```text
AFTERBELL noticed a material change on NVDABUSDT.

Reference market: RTH_OPEN -> CLOSED_WEEKEND
Safety posture: Clear -> Smaller size

The market that supplies the independent price changed session.
The size AFTERBELL is willing to stand behind changed as a result.

Nobody asked for this. No order was created and no authorization was issued;
a request is still evaluated on its own merits when one arrives.
```

A band moving is material by construction: it is a boundary the limits already
change their answer at, not a threshold invented for reporting. The dashboard
shows these under **Noticed without being asked**, and an agent can read them
through the `get_safety_posture` tool before it proposes anything.

What this deliberately is not: it never originates an order, and it never signs
a standing permission. An authorization is bound to one specific proposal — its
symbol, side, requested and permitted size, the evidence behind it, an expiry
and a one-time nonce. A background observation has no proposal behind it, so
there is nothing to bind and nothing is signed. When an agent does propose an
order, the request-specific path decides what it may do, against the picture
that is current by then.

## Current live checkpoint

This is the state observed on **8 September 2026 UTC**; the dashboard is the
live source for changing counters and timestamps.

| What a reviewer can verify | Current state |
|---|---|
| Supported instruments | 5 token pairs with checked registry entries |
| Measured books / reference prints | 39,895 / 36,045 in the published data report |
| Normal-hours data coverage | 868 observations per token; 300 required |
| Holiday data coverage | 1,440 observations per token |
| Recorded decisions | 6,790+ live receipts |
| Order limit | $5,000 base request; market checks can reduce it |
| Current decision | $0 allowed because a recent signed account-position report was not supplied |
| Data archive | Live and updating |
| Python-side exchange credentials | None |

The zero amount is not a market prediction. It means AFTERBELL cannot safely
measure existing account exposure, so it refuses to assume the account is empty.

## Configure the order limit

The dashboard shows the current maximum for one request. Set
`base_notional_usdt` in [`config/policy.yaml`](config/policy.yaml) when you
want a different maximum. The market checks can always choose a smaller amount
when timing, liquidity, price agreement, instrument identity, or account
exposure calls for caution.

This keeps the important choice visible: the configured amount is the starting
point, and the measured market decides whether the request can use all of it.

## The seven plain-language checks

| Check | Question it answers |
|---|---|
| Market timing | How old is the reference, and how long until the underlying market can print again? |
| Liquidity | Can the requested amount be filled without an unusually expensive or thin book? |
| Price agreement | How far apart are the token and the latest independent reference price? |
| Corporate-action status | Does the venue report a current restriction or processing message? |
| Instrument identity | Is this the exact certificate, issuer, network, and underlying the request names? |
| Contract address | Does the address match the checked canonical registry? |
| Account exposure | Do we have a recent, trusted view of current holdings before adding more? |

The checks produce independent ceilings. The permitted amount is the smallest
of them, never a product of several uncertain estimates. A single unknown that
could make the request unsafe can reduce the amount to zero.

## Why the account report matters

The account-exposure check is simple to explain: before adding a new position,
the system must know what the account already holds across the supported
symbols. A recent signed position report supplies that fact without giving
AFTERBELL an exchange login.

If the report is missing, stale, unsigned, or altered, the safe answer is not
“the account is empty.” The safe answer is “I cannot measure this request,” and
new exposure is refused. The public dashboard calls this **required account
report missing** and explains the consequence directly.

The report contains signed USDT notionals, not credentials. The raw positions
are not written into public receipts; only the report identity and verification
result are retained.

## What the permitted size is, and what it binds

A request meets four ceilings, and each one can only lower the number:

```text
the agent asks                            5,000 USDT   base_notional_usdt
the market checks decide                  measured     timing, liquidity, price,
                                                       status, identity, address
account-risk ceiling                        100 USDT   exposure.max_gross_usdt
signed execution ceiling                     25 USDT   executor.max_order_usdt
```

The agent asking for 5,000 does not mean 5,000 can move. The account-risk
ceiling is how much certificate exposure this deployment is willing to
accumulate at all; the execution ceiling is a separate number chosen by hand so
that a mistake anywhere in the sizing chain is still bounded. Both are stored in
the signed settings file whose SHA-256 is written into every receipt, so a
limit that moved is visible in the evidence rather than only in the code.

**What the authorization binds, precisely.** AFTERBELL signs a short-lived,
single-use authorization and records it. A supported client transcribes that
artifact and submits exactly what it permits, and the redemption record carries
requested, permitted and actually-spent side by side, read back from the venue
response rather than assumed.

What that does **not** mean: the venue's own MCP server does not verify
AFTERBELL's signature, and the OAuth session belongs to the supported client,
not to this package. A client that ignored AFTERBELL could call its own trading
tool directly. So the guarantee is about the governed handoff — *that path never
produces an order larger than AFTERBELL permitted, and the ledger shows what was
actually spent* — and not a cryptographic restriction on every action available
to the client's credential. Binding that credential would mean holding it, which
is the one thing this package refuses to do.

## Why the design is trustworthy

- **Deterministic:** measurements and decisions are produced by ordinary code,
  not generated by a model.
- **Conservative:** missing reference data, missing liquidity data, an
  unknown instrument, an unsafe status, or missing account evidence cannot
  silently become a clear result.
- **Traceable:** every decision and refusal enters an append-only, hash-linked
  receipt ledger.
- **Credential-separated:** the recorder, dashboard, and evaluator hold no
  exchange credential. The dashboard only measures and explains requests.
- **Hard to persuade:** the signed settings file is loaded independently of the
  request text. Urgency, authority claims, fabricated prices, and prompt
  injection cannot raise an amount.
- **Observable:** the public dashboard shows both normal outcomes and refusals,
  plus the data age and integrity identifiers needed to interpret them.

## Evidence, not marketing

The current generated safety report records:

- 35 hostile request patterns tested against two market states;
- zero hostile inputs that raised the permitted amount above its control;
- 6/6 positive controls, demonstrating that the suite cannot “succeed” by
  refusing every request;
- 99 of 100 normal-book requests permitted at full requested size;
- a measured 1.00% refusal rate inside that specifically defined normal-book
  cohort, the single case being the designed closing-bell ramp;
- 10 refusals for a missing signed account report, counted and published
  separately because they are refusals on an absent input rather than on a
  measurement; and
- six recorder and measurement issues found by the project's own tooling
  and then fixed.

The 1.00% figure is not a claim about all order flow. The monitor repeatedly
probed the same 5,000 USDT request once a minute. The definition and exclusions
are published in [`docs/evaluation.md`](docs/evaluation.md).

The counterparty-composition question is intentionally not given a direction:
historical trade capture was uneven before the recorder fix, so the honest
result is “not enough balanced evidence yet.” The limitation is documented in
[`docs/counterparty.md`](docs/counterparty.md).

## Run it locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m afterbell.engine \
  --symbol NVDABUSDT --notional 5000 --query "buy Nvidia"
```

Use the package as a small boundary around an existing agent:

```python
from afterbell.engine import Guard
from afterbell.guard import OrderRequest
from afterbell.measure import Side

guard = Guard.from_policy("config/policy.yaml")
decision = guard.evaluate(
    OrderRequest("NVDABUSDT", Side.BUY, 5000.0, query="buy Nvidia")
)
print(decision.allowed_notional, decision.rationale)
```

The public MCP endpoint provides `evaluate_order`, `get_market_state` and
`get_safety_posture`. The public dashboard and MCP server do not place an order.

## Read next

- [Live dashboard](https://afterbell.site) — the fastest way to see the system.
- [`docs/calibration.md`](docs/calibration.md) — measured market baselines and
  price-difference distributions.
- [`docs/evaluation.md`](docs/evaluation.md) — safety-test definitions and
  generated results.
- [`docs/live-acceptance.md`](docs/live-acceptance.md) — the one recorded,
  recorded minimum-size acceptance event.
- [`docs/position-input.md`](docs/position-input.md) — how a supported client
  supplies a signed account-position report without sharing credentials.
- [`docs/submission-checklist.md`](docs/submission-checklist.md) — evidence that
  is ready and work that still needs an external destination.
- [`STATUS.md`](STATUS.md) — current operations and known limitations.

## Important boundaries

AFTERBELL is a technical demonstration, not investment advice, an offer, a
solicitation, or a claim of direct ownership of an underlying share. Tokenized
securities are certificates with risks distinct from the securities they
reference.

The corporate-action signal is a live current-status check. It does not claim
guaranteed advance notice of every future event. Backup verification confirms
stable files at a checked point; it is not an atomic remote snapshot of hot
files. The underlying U.S. market calendar and the public token venue can both
change, so the timestamps and source links on the dashboard matter.

## License

MIT. Technical demonstration only.
