"""Real transaction costs, so backtests are net of what actually gets deducted.

Backtests took a flat `fee_bps` per side, which is a guess. Costs turned out to matter:
sweeping the swing engine over 124 symbols, going from zero costs to an estimated 40bps
round trip moved the median return from -2.79% to -6.08%. A strategy sitting near zero is
decided by this number, so it should be the real schedule rather than a placeholder.

Indian charges are the awkward ones — six separate line items, several asymmetric between
buy and sell, one of them a flat rupee amount that scales inversely with trade size. Rates
below are the published NSE/SEBI schedule, cross-checked against the cost model in
ajeeshworkspace/indian-trading-skills (MIT).

Rates change with budgets and SEBI circulars. `as_of` is stamped on every result so a
stale schedule is visible rather than silently assumed.
"""
from __future__ import annotations

RATES_AS_OF = "2026-08"

# Flat brokerage per order at a discount broker. Delivery is typically free; intraday and
# F&O are the lower of Rs 20 or 0.03%. This is the line item that makes small trades
# disproportionately expensive.
BROKERAGE_FLAT = {"delivery": 0.0, "intraday": 20.0, "fno_futures": 20.0,
                  "fno_options": 20.0}

# (buy_rate, sell_rate) as fractions of turnover.
STT = {"delivery": (0.001, 0.001),       # 0.1% both sides
       "intraday": (0.0, 0.00025),       # sell only
       "fno_futures": (0.0, 0.000125),
       "fno_options": (0.0, 0.000125)}   # on premium
STAMP_DUTY_BUY = {"delivery": 0.00015, "intraday": 0.00003,
                  "fno_futures": 0.00002, "fno_options": 0.00003}
EXCHANGE_RATE = {"delivery": 0.0000345, "intraday": 0.0000345,
                 "fno_futures": 0.0000173, "fno_options": 0.0005}
SEBI_RATE = 0.000001          # both sides
GST_RATE = 0.18               # on brokerage + exchange charges only, not on STT

TRADE_TYPES = tuple(STT)


def india_costs(trade_value: float, trade_type: str = "delivery") -> dict:
    """Round-trip cost for one Indian equity/F&O trade of `trade_value` per side.

    Returns absolute rupees per line item plus `total_pct`, the round-trip cost as a
    percentage of one side's turnover — which is the form a backtest can apply.
    """
    if trade_type not in TRADE_TYPES:
        raise ValueError(f"unknown trade_type {trade_type!r}; expected one of {TRADE_TYPES}")
    if trade_value <= 0:
        raise ValueError("trade_value must be positive")

    brokerage = BROKERAGE_FLAT[trade_type] * 2          # one order each way
    buy_stt, sell_stt = STT[trade_type]
    stt = trade_value * (buy_stt + sell_stt)
    exchange = trade_value * EXCHANGE_RATE[trade_type] * 2
    # GST applies to brokerage and exchange charges. It does NOT apply to STT or stamp
    # duty — taxing a tax is a common and material error in home-grown cost models.
    gst = (brokerage + exchange) * GST_RATE
    stamp = trade_value * STAMP_DUTY_BUY[trade_type]    # buy side only
    sebi = trade_value * SEBI_RATE * 2

    # Total is summed from the *rounded* components so the breakdown adds up. Rounding
    # each line and the raw total independently leaves them a paisa apart, which looks
    # like a bug to anyone checking the arithmetic by hand.
    parts = {"brokerage": round(brokerage, 2), "stt": round(stt, 2),
             "exchange": round(exchange, 2), "gst": round(gst, 2),
             "stamp_duty": round(stamp, 2), "sebi": round(sebi, 2)}
    total = round(sum(parts.values()), 2)
    return {**parts, "total": total,
            "total_pct": round(total / trade_value * 100, 4),
            "trade_type": trade_type, "trade_value": trade_value, "as_of": RATES_AS_OF}


# US equities at a zero-commission broker: SEC fee and FINRA TAF are sell-side only and
# tiny. Kept deliberately simple — the US universe here is 18 large caps where spreads,
# not fees, dominate.
US_SELL_SIDE = 0.0000278 + 0.000166      # SEC fee + FINRA TAF, fractions of value


def us_costs(trade_value: float) -> dict:
    total = trade_value * US_SELL_SIDE
    return {"total": round(total, 2), "total_pct": round(total / trade_value * 100, 4),
            "trade_type": "us_equity", "trade_value": trade_value, "as_of": RATES_AS_OF}


def round_trip_pct(trade_value: float, market: str = "IN",
                   trade_type: str = "delivery") -> float:
    """Round-trip cost as a percent of turnover — the one number a backtest needs."""
    if market == "IN":
        return india_costs(trade_value, trade_type)["total_pct"]
    return us_costs(trade_value)["total_pct"]
