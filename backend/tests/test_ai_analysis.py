"""Covers the context shaping that keeps the narrative honest — the derived-facts block
and the signal_direction/trade_plan split. The LLM paths aren't exercised here (no network);
_rule_based is, since it's the fallback every provider failure lands on."""
import pytest

from app.services import ai_analysis as ai


BASE_ANALYSE = {
    "close": 100.0, "rsi": 50.0, "ema20": 101.0, "ema50": 102.0, "atr": 2.0, "rvol": 1.0,
    "trend": "DOWN", "signals": [], "score": 0.0, "direction": "LONG",
    "entry": 100.0, "stop": 97.0, "target": 106.0,
}


@pytest.fixture
def ctx_factory(monkeypatch, make_df):
    """Build a _context() dict without touching the DB or yfinance."""
    def _make(**analyse_overrides):
        a = {**BASE_ANALYSE, **analyse_overrides}
        closes = [90.0 + i * 0.05 for i in range(300)]
        monkeypatch.setattr(ai, "analyse", lambda s: a)
        monkeypatch.setattr(ai, "get_candles", lambda s: make_df(closes))
        monkeypatch.setattr(ai, "get_symbol", lambda s: {
            "symbol": s, "name": "Test Co", "market": "IN", "sector": "IT",
            "pe": 23.0, "roe": None, "de": 0.4, "rev_growth": 10.0,
            "div_yield": 0.5, "mcap": 1e12})
        monkeypatch.setattr(ai, "ticker_news", lambda s, n=5: [])
        return ai._context("TEST")
    return _make


# ---- signal_direction vs trade_plan.direction -------------------------------

def test_no_signal_means_null_direction_not_long(ctx_factory):
    """signals.analyse() defaults direction to LONG so the risk calculator always has a
    plan. Surfacing that as a real direction made the narrative call flat tape bullish."""
    ctx = ctx_factory(signals=[], score=0.0, direction="LONG")
    assert ctx["signal_direction"] is None
    assert ctx["trade_plan"]["direction"] == "LONG"   # plan still loadable
    assert "direction" not in ctx                     # the ambiguous field is gone


def test_fired_signal_carries_its_direction(ctx_factory):
    ctx = ctx_factory(signals=[{"type": "BUY", "why": "breakout"}], score=2.0, direction="LONG")
    assert ctx["signal_direction"] == "LONG"
    ctx = ctx_factory(signals=[{"type": "SELL", "why": "breakdown"}], score=2.0, direction="SHORT")
    assert ctx["signal_direction"] == "SHORT"


def test_rule_based_will_not_claim_alignment_with_no_signal(ctx_factory):
    """The exact regression: a bullish strategy on flat tape must not read as backed."""
    ctx = ctx_factory(signals=[], score=0.0, direction="LONG")
    ctx["strategy"] = {"name": "Bull Call Spread", "desc": "Bullish. Capped risk and reward.",
                       "legs": [{"type": "call", "strike": 100, "qty": 1, "premium": 3.0}],
                       "net_premium": 3.0, "max_profit": "5.00", "max_loss": "3.00",
                       "breakevens": [103.0], "breakevens_vs_range": "all inside the 20-day range",
                       "days_to_expiry": 30, "realized_vol_pct": 20.0, "position_greeks": None}
    out = ai._rule_based(ctx)
    assert "isn't backed by a triggered rule" in out
    assert "agrees with" not in out


def test_rule_based_reports_agreement_when_a_signal_actually_fired(ctx_factory):
    ctx = ctx_factory(signals=[{"type": "BUY", "why": "breakout"}], score=2.0, direction="LONG")
    ctx["strategy"] = {"name": "Bull Call Spread", "desc": "Bullish. Capped risk and reward.",
                       "legs": [{"type": "call", "strike": 100, "qty": 1, "premium": 3.0}],
                       "net_premium": 3.0, "max_profit": "5.00", "max_loss": "3.00",
                       "breakevens": [103.0], "breakevens_vs_range": None,
                       "days_to_expiry": 30, "realized_vol_pct": 20.0, "position_greeks": None}
    assert "agrees with" in ai._rule_based(ctx)


# ---- derived facts ----------------------------------------------------------

@pytest.mark.parametrize("rsi,zone", [(20, "oversold"), (48.8, "neutral"), (80, "overbought")])
def test_rsi_zone_classification(rsi, zone):
    assert ai._rsi_zone(rsi) == zone


@pytest.mark.parametrize("rvol,note", [
    (2.0, "unusually heavy"), (1.2, "above average"),
    (1.02, "about average"), (0.5, "below average")])
def test_rvol_note_classification(rvol, note):
    """1.02 must not read as elevated — llama3 called it 'relatively high'."""
    assert ai._rvol_note(rvol) == note


def test_range_note_detects_inside_vs_outside():
    assert "all inside" in ai._range_note([105.0], 100.0, 110.0)
    outside = ai._range_note([95.0, 105.0], 100.0, 110.0)
    assert "outside" in outside and "95.00" in outside and "105.00" not in outside
    assert ai._range_note([], 100.0, 110.0) is None


def test_derived_block_is_populated(ctx_factory):
    ctx = ctx_factory(rsi=48.8, rvol=1.02)
    d = ctx["derived"]
    assert d["rsi_zone"] == "neutral"
    assert d["volume_vs_20d_average"] == "about average"
    assert d["ema_stack"] == "bearish (20<50)"       # 101 < 102
    assert d["any_signal_fired"] is False
    assert d["price_vs_sma200"] in ("above", "below", None)


def test_rule_based_and_derived_agree(ctx_factory):
    """Both paths must classify identically or the two narratives contradict."""
    ctx = ctx_factory(rsi=48.8, rvol=1.02)
    out = ai._rule_based(ctx)
    assert ctx["derived"]["rsi_zone"] in out
    assert ctx["derived"]["volume_vs_20d_average"] in out


# ---- provider chain ---------------------------------------------------------

def test_falls_through_to_rules_and_reports_failures(ctx_factory, monkeypatch):
    ctx = ctx_factory()
    monkeypatch.setattr(ai, "_providers",
                        lambda: [("ollama", "llama3", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))])
    res = ai._run(ctx, ai.SYSTEM, "stock")
    assert res["source"] == "rules"
    assert "ollama (RuntimeError)" in res["note"]
    assert res["direction"] is None          # no signal fired in the fixture


def test_first_working_provider_wins(ctx_factory, monkeypatch):
    ctx = ctx_factory()
    monkeypatch.setattr(ai, "_providers", lambda: [
        ("claude", "m1", lambda *a: (_ for _ in ()).throw(RuntimeError("down"))),
        ("ollama", "llama3", lambda *a: "local narrative"),
    ])
    res = ai._run(ctx, ai.SYSTEM, "stock")
    assert res["source"] == "ollama" and res["analysis"] == "local narrative"
    assert "note" not in res   # a recovered failure isn't worth surfacing
