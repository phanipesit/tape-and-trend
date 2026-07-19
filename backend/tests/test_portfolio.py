from app.routers.portfolio import _replay, _stats, _setup_stats

def tx(symbol, side, qty, price, i=0, setup="", notes=""):
    return {"id": i, "symbol": symbol, "side": side, "qty": qty, "price": price,
            "setup": setup, "notes": notes, "traded_at": f"2026-01-{i + 1:02d}"}

def test_replay_simple_round_trip():
    hold, realized = _replay([tx("A", "BUY", 10, 100, 1), tx("A", "SELL", 10, 110, 2)])
    assert hold["A"]["qty"] == 0
    assert len(realized) == 1
    r = realized[0]
    assert r["pnl"] == 100.0 and r["ret_pct"] == 10.0 and r["avg_in"] == 100.0

def test_replay_average_cost_partial_sell():
    hold, realized = _replay([tx("A", "BUY", 10, 100, 1), tx("A", "BUY", 10, 200, 2),
                              tx("A", "SELL", 5, 180, 3)])
    r = realized[0]
    assert r["avg_in"] == 150.0
    assert r["pnl"] == 150.0                  # (180-150) * 5
    assert hold["A"]["qty"] == 15
    assert hold["A"]["cost"] == 2250.0        # remaining at avg cost

def test_replay_oversell_is_clamped():
    hold, realized = _replay([tx("A", "BUY", 10, 100, 1), tx("A", "SELL", 25, 110, 2)])
    assert realized[0]["qty"] == 10           # can't close more than held
    assert hold["A"]["qty"] == 0

def test_stats_math():
    realized = [{"ret_pct": 10.0, "pnl": 1}, {"ret_pct": -5.0, "pnl": -1},
                {"ret_pct": 20.0, "pnl": 2}, {"ret_pct": -10.0, "pnl": -2}]
    st = _stats(realized)
    assert st["n"] == 4 and st["win_rate"] == 50.0
    assert st["avg_win_pct"] == 15.0 and st["avg_loss_pct"] == -7.5
    assert st["expectancy_pct"] == 3.75       # 0.5*15 + 0.5*(-7.5)
    assert st["best_pct"] == 20.0 and st["worst_pct"] == -10.0

def test_stats_empty():
    assert _stats([]) == {"n": 0}

def test_setup_stats_groups_and_sorts():
    realized = [
        {"setup": "Breakout", "ret_pct": 10.0, "pnl": 100},
        {"setup": "Breakout", "ret_pct": -5.0, "pnl": -50},
        {"setup": "RSI pullback", "ret_pct": 20.0, "pnl": 200},
        {"setup": "", "ret_pct": 1.0, "pnl": 10},
    ]
    out = _setup_stats(realized)
    assert [s["setup"] for s in out] == ["RSI pullback", "Breakout", "untagged"]
    b = next(s for s in out if s["setup"] == "Breakout")
    assert b["n"] == 2 and b["win_rate"] == 50.0
    assert b["avg_ret_pct"] == 2.5 and b["total_pnl"] == 50.0
