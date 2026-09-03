"""AFTERBELL - a calendar-aware risk boundary for tokenized equities.

The stock sleeps. The token doesn't.

The adoption shape is four lines around an existing agent, with the trading
logic untouched, so those four lines must work from this package directly:

    from afterbell import Guard, OrderRequest, Side

    guard = Guard.from_policy("config/policy.yaml")
    decision = guard.evaluate(OrderRequest("NVDABUSDT", Side.BUY, 5000.0,
                                           query="buy Nvidia"))
    if decision.allowed_notional > 0:
        mcp.place_order(order.at(decision.allowed_notional))

Importing this module pulls in no credential and opens no connection.
"""
from afterbell.engine import Guard
from afterbell.guard import Decision, OrderRequest, Verdict
from afterbell.measure import Side

__version__ = "0.1.0"
__all__ = ["Guard", "OrderRequest", "Decision", "Verdict", "Side"]
