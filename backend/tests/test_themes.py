"""Theme tracker. Pure arithmetic — q() is monkeypatched, nothing touches the network."""
import pytest

from app.services import themes


def rows_for(spec):
    """spec: {symbol: (sector, {year: (revenue, net_income)})}"""
    out = []
    for sym, (sector, years) in spec.items():
        for y, (rev, ni) in years.items():
            out.append({"symbol": sym, "fiscal_year": y, "revenue": rev,
                        "net_income": ni, "sector": sector, "name": sym, "market": "IN"})
    return out


def steady(base=100.0, rate=0.10, n=5, margin=0.10, last_rate=None):
    """n years compounding at `rate`, optionally with a different final year."""
    years, rev = {}, base
    for i in range(n):
        r = last_rate if (last_rate is not None and i == n - 1) else rate
        rev = rev * (1 + r) if i else rev
        years[2022 + i] = (rev, rev * margin)
    return years


def run(spec, monkeypatch, market=None):
    monkeypatch.setattr(themes, "q", lambda sql, **kw: rows_for(spec))
    return themes.board(market)


# ---------------------------------------------------------------- acceleration

def test_acceleration_is_latest_year_against_its_own_trend(monkeypatch):
    """A fast-growing sector must not outrank a slow one merely for being fast — each
    company is measured against itself."""
    spec = {f"FAST{i}": ("IT Services", steady(rate=0.30, last_rate=0.30)) for i in range(3)}
    spec |= {f"INFL{i}": ("Metals & Mining", steady(rate=0.02, last_rate=0.20)) for i in range(3)}
    r = run(spec, monkeypatch)
    top = r["themes"][0]
    assert top["theme"] == "Metals & Mining"      # inflecting, not merely fast
    assert top["accel"] > 0


def test_steady_compounding_shows_no_acceleration(monkeypatch):
    spec = {f"S{i}": ("IT Services", steady(rate=0.20)) for i in range(3)}
    r = run(spec, monkeypatch)
    assert r["themes"][0]["accel"] == pytest.approx(0.0, abs=1e-6)


def test_deceleration_is_reported_negative(monkeypatch):
    spec = {f"D{i}": ("Banking", steady(rate=0.20, last_rate=0.02)) for i in range(3)}
    assert run(spec, monkeypatch)["themes"][0]["accel"] < 0


# ---------------------------------------------------------------- robustness

def test_a_single_outlier_cannot_carry_a_theme(monkeypatch):
    """Medians throughout: one company tripling revenue would otherwise define the sector."""
    spec = {"FLAT1": ("FMCG", steady(rate=0.05)), "FLAT2": ("FMCG", steady(rate=0.05)),
            "MOON": ("FMCG", steady(rate=0.05, last_rate=3.0))}
    r = run(spec, monkeypatch)
    t = r["themes"][0]
    assert t["accel"] == pytest.approx(0.0, abs=1e-6)   # median unmoved
    assert t["breadth"] == pytest.approx(1/3, abs=0.01)  # but breadth shows only one moved


def test_thin_themes_are_excluded(monkeypatch):
    spec = {"ONLY": ("Telecom", steady())}
    assert run(spec, monkeypatch)["themes"] == []


def test_companies_with_too_little_history_are_dropped(monkeypatch):
    spec = {f"NEW{i}": ("FMCG", steady(n=2)) for i in range(3)}
    assert run(spec, monkeypatch)["themes"] == []


def test_zero_or_negative_base_revenue_does_not_explode(monkeypatch):
    spec = {f"Z{i}": ("Energy", {2022: (0.0, 0.0), 2023: (10.0, 1.0),
                                 2024: (20.0, 2.0), 2025: (30.0, 3.0)}) for i in range(3)}
    assert run(spec, monkeypatch)["themes"] == []      # skipped, not infinite growth


# ---------------------------------------------------------------- margins & AI

def test_margin_direction_is_tracked_alongside_growth(monkeypatch):
    """Revenue accelerating while margins collapse is buying growth, not earning it."""
    years = {2022: (100.0, 20.0), 2023: (120.0, 20.0),
             2024: (150.0, 18.0), 2025: (220.0, 11.0)}
    spec = {f"B{i}": ("Consumer", years) for i in range(3)}
    t = run(spec, monkeypatch)["themes"][0]
    assert t["accel"] > 0 and t["margin_change"] < 0


def test_ai_theme_is_orthogonal_to_its_sector(monkeypatch):
    """A semiconductor company is both a semiconductor company and part of the AI trade."""
    spec = {f"CHIP{i}": ("Semiconductors", steady(rate=0.10, last_rate=0.40))
            for i in range(3)}
    names = [t["theme"] for t in run(spec, monkeypatch)["themes"]]
    assert "Semiconductors" in names and themes.AI_LABEL in names


def test_ai_members_are_not_double_counted_in_the_company_total(monkeypatch):
    spec = {f"CHIP{i}": ("Semiconductors", steady()) for i in range(3)}
    assert run(spec, monkeypatch)["companies"] == 3
