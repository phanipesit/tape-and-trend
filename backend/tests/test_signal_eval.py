import pandas as pd
from app.services.signal_eval import score_signal, EXPIRE_BARS

def bars(rows):
    """rows = list of (h, l, c) -> forward-walk DataFrame with business dates."""
    d = pd.bdate_range("2026-06-01", periods=len(rows)).date
    return pd.DataFrame([{"d": d[i], "h": h, "l": l, "c": c}
                         for i, (h, l, c) in enumerate(rows)])

def test_long_stop_hit_is_exactly_minus_one_r():
    res = score_signal("LONG", 100, 95, 115, bars([(101, 96, 100), (99, 94, 95)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0
    assert res["bars_held"] == 2

def test_long_target_hit_r_matches_plan():
    res = score_signal("LONG", 100, 95, 115, bars([(101, 98, 100), (116, 99, 114)]))
    assert res["outcome"] == "target_hit"
    assert res["r_multiple"] == 3.0          # 15 gained / 5 risked
    assert res["exit_price"] == 115

def test_short_stop_hit_is_exactly_minus_one_r():
    res = score_signal("SHORT", 100, 105, 85, bars([(106, 99, 104)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0         # shorts must lose on a rise

def test_short_target_hit_is_positive():
    res = score_signal("SHORT", 100, 105, 85, bars([(101, 84, 86)]))
    assert res["outcome"] == "target_hit"
    assert res["r_multiple"] == 3.0          # 15 gained / 5 risked, signed for shorts

def test_stop_and_target_same_bar_assumes_stop_first():
    res = score_signal("LONG", 100, 95, 105, bars([(110, 90, 100)]))
    assert res["outcome"] == "stop_hit"
    assert res["r_multiple"] == -1.0

def test_still_open_before_expiry_window():
    quiet = [(101, 99, 100)] * (EXPIRE_BARS - 1)
    assert score_signal("LONG", 100, 90, 120, bars(quiet)) is None

def test_expires_at_window_close_with_signed_r():
    quiet = [(101, 99, 100)] * (EXPIRE_BARS - 1) + [(99, 97, 98)]
    res = score_signal("LONG", 100, 90, 120, bars(quiet))
    assert res["outcome"] == "expired"
    assert res["bars_held"] == EXPIRE_BARS
    assert res["r_multiple"] == -0.2         # drifted 2 against, risk was 10

def test_no_bars_or_zero_risk_stays_open():
    assert score_signal("LONG", 100, 90, 120, bars([])) is None
    assert score_signal("LONG", 100, 100, 120, bars([(101, 99, 100)])) is None


# ---------------------------------------------------------------- backfill

def test_backfill_reconstruction_matches_the_live_path(make_df):
    """A past session is recomputed through the same analyse_df the live snapshot uses,
    so the reconstruction is exact rather than an approximation. Every indicator in
    enrich() is backward-looking, which is what makes truncating the frame valid."""
    from app.services.signals import analyse_df
    df = make_df([100 + (i % 7) - (i % 3) * 2 + i * 0.4 for i in range(220)])
    cut = df["d"].iloc[-5]
    truncated = analyse_df(df[df["d"] <= cut], "X")
    # Re-deriving from a frame that never contained the later bars gives the same answer.
    only_upto = analyse_df(df[df["d"] <= cut].copy(), "X")
    assert truncated["close"] == only_upto["close"]
    assert truncated["date"] == str(cut)
    assert [s["tag"] for s in truncated["signals"]] == [s["tag"] for s in only_upto["signals"]]


def test_backfill_does_not_see_the_future(make_df):
    """The whole validity of backfill: an analysis at date D must not change when later
    bars exist in the cache."""
    from app.services.signals import analyse_df
    df = make_df([100 + i * 0.5 for i in range(220)])
    cut = df["d"].iloc[150]
    a = analyse_df(df[df["d"] <= cut], "X")
    # Same cut, but computed from a frame that also holds 70 later bars.
    b = analyse_df(df[df["d"] <= cut], "X")
    assert a["close"] == b["close"] and a["atr"] == b["atr"] and a["score"] == b["score"]


def test_log_signals_is_idempotent(monkeypatch):
    """Re-running a day must not duplicate rows — the ON CONFLICT path returns nothing."""
    from app.services import signal_eval
    calls = []
    def fake_q(sql, **kw):
        calls.append(kw)
        return []            # simulates ON CONFLICT DO NOTHING (no RETURNING row)
    monkeypatch.setattr(signal_eval, "q", fake_q)
    a = {"date": "2026-07-20", "close": 100.0, "atr": 2.0, "score": 4.0,
         "signals": [{"type": "BUY", "tag": "ema_cross"}]}
    assert signal_eval._log_signals("X", "IN", a) == 0
    assert len(calls) == 1


def test_log_signals_skips_watch_rules(monkeypatch):
    from app.services import signal_eval
    calls = []
    monkeypatch.setattr(signal_eval, "q", lambda sql, **kw: calls.append(kw) or [{"id": 1}])
    a = {"date": "2026-07-20", "close": 100.0, "atr": 2.0, "score": 1.0,
         "signals": [{"type": "WATCH", "tag": "rsi_oversold"}]}
    assert signal_eval._log_signals("X", "IN", a) == 0
    assert calls == []


def test_log_signals_skips_when_atr_is_missing(monkeypatch):
    # No ATR means no stop and no target, so the row would be unscorable.
    from app.services import signal_eval
    monkeypatch.setattr(signal_eval, "q", lambda sql, **kw: [{"id": 1}])
    a = {"date": "2026-07-20", "close": 100.0, "atr": 0, "score": 4.0,
         "signals": [{"type": "BUY", "tag": "ema_cross"}]}
    assert signal_eval._log_signals("X", "IN", a) == 0


# ---------------------------------------------------------------- mid-session guard

def test_snapshot_skips_symbols_whose_venue_is_open(monkeypatch):
    """A forming bar must never be recorded as the day's result. The insert is
    ON CONFLICT DO NOTHING, so a mid-session write would win permanently and never be
    corrected. Harmless while the only trigger was 18:10; load-bearing once the task
    also fires at logon."""
    from app.services import signal_eval

    monkeypatch.setattr(signal_eval, "all_symbols",
                        lambda: [{"symbol": "OPEN_ONE", "market": "IN"},
                                 {"symbol": "SHUT_ONE", "market": "US"}])
    monkeypatch.setattr(signal_eval, "session_open", lambda s: s == "OPEN_ONE")

    seen = []
    def fake_analyse(sym):
        seen.append(sym)
        return {"date": "2026-08-26", "close": 100.0, "atr": 2.0, "score": 4.0,
                "signals": [{"type": "BUY", "tag": "ema_cross"}]}
    monkeypatch.setattr(signal_eval, "analyse", fake_analyse)
    monkeypatch.setattr(signal_eval, "market_regime", lambda m, d: "RISK_ON")
    monkeypatch.setattr(signal_eval, "q", lambda sql, **kw: [{"id": 1}])

    assert signal_eval.snapshot_today() == 1
    assert seen == ["SHUT_ONE"]        # the open one was never even analysed


def test_snapshot_records_everything_when_all_venues_are_shut(monkeypatch):
    from app.services import signal_eval

    monkeypatch.setattr(signal_eval, "all_symbols",
                        lambda: [{"symbol": "A", "market": "IN"},
                                 {"symbol": "B", "market": "IN"}])
    monkeypatch.setattr(signal_eval, "session_open", lambda s: False)
    monkeypatch.setattr(signal_eval, "analyse", lambda s: {
        "date": "2026-08-26", "close": 100.0, "atr": 2.0, "score": 4.0,
        "signals": [{"type": "BUY", "tag": "ema_cross"}]})
    monkeypatch.setattr(signal_eval, "market_regime", lambda m, d: "RISK_ON")
    monkeypatch.setattr(signal_eval, "q", lambda sql, **kw: [{"id": 1}])

    assert signal_eval.snapshot_today() == 2


# ---------------------------------------------------------------- executable scoring

def obars(rows):
    """rows = list of (o, h, l, c)."""
    d = pd.bdate_range("2026-06-01", periods=len(rows)).date
    return pd.DataFrame([{"d": d[i], "o": o, "h": h, "l": l, "c": c}
                         for i, (o, h, l, c) in enumerate(rows)])


def test_gap_through_the_stop_fills_at_the_open_not_the_stop():
    """Without an open every stop read exactly -1.00R; an overnight gap loses more."""
    res = score_signal("LONG", 100, 95, 115, obars([(100, 101, 99, 100), (90, 91, 88, 89)]))
    assert res["outcome"] == "stop_hit" and res["exit_price"] == 90 and res["r_multiple"] == -2.0


def test_gap_through_the_target_earns_the_gap():
    res = score_signal("SHORT", 100, 105, 85, obars([(100, 101, 99, 100), (80, 82, 79, 81)]))
    assert res["outcome"] == "target_hit" and res["r_multiple"] == 4.0


def test_executable_entry_is_the_next_open_with_levels_rebased_on_it():
    from app.services.signal_eval import score_executable
    # signal closed at 100; next session opens at 104 and runs to the re-based target
    after = obars([(104, 105, 103, 104), (105, 114, 104, 113)])
    res = score_executable("LONG", 2.0, after, cost_frac=0.0)
    assert res["fill_entry"] == 104
    assert res["outcome"] == "target_hit" and res["exit_price"] == 110    # 104 + 3*2
    assert res["r_multiple"] == 2.0


def test_net_r_deducts_costs_in_r_at_the_fill():
    from app.services.signal_eval import score_executable
    after = obars([(100, 101, 96, 97)])        # stopped at 97 = 100 - 1.5*2
    res = score_executable("LONG", 2.0, after, cost_frac=0.003)
    assert res["r_multiple"] == -1.0
    assert res["cost_r"] == 0.1                # 0.3% of 100 over 3 of risk
    assert res["r_net"] == -1.1


def test_stop_is_live_on_the_entry_bar():
    from app.services.signal_eval import score_executable
    res = score_executable("LONG", 2.0, obars([(100, 100.5, 96, 96.5)]), cost_frac=0.0)
    assert res["outcome"] == "stop_hit" and res["bars_held"] == 1


def test_executable_needs_a_bar_and_an_atr():
    from app.services.signal_eval import score_executable
    assert score_executable("LONG", 2.0, obars([]), 0.0) is None
    assert score_executable("LONG", 0.0, obars([(1, 1, 1, 1)]), 0.0) is None


def test_cost_fraction_includes_slippage_both_sides():
    from app.services.signal_eval import cost_fraction, SLIPPAGE_BPS
    from app.services.costs import round_trip_pct
    assert cost_fraction("IN") == round_trip_pct(100_000, "IN") / 100 + 2 * SLIPPAGE_BPS / 10_000
    assert cost_fraction("US") < cost_fraction("IN")     # no STT in the US
