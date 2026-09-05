"""Quality screen: seven exclusion tests. Pure — evaluate() takes rows, touches nothing."""
import pytest

from app.services import quality


def year(y, **kw):
    base = {"fiscal_year": y, "revenue": 1000.0, "gross_profit": 400.0,
            "net_income": 100.0, "ebit": 150.0, "interest_expense": -10.0,
            "operating_cf": 120.0, "capex": -20.0, "free_cf": 100.0,
            "shares": 1000.0, "equity": 500.0}
    base.update(kw)
    return base


def good(n=5, **kw):
    return [year(2026 - i, **kw) for i in range(n)]


def run(rows, sector=None):
    return quality.evaluate("X", rows, sector)


def status(res, n):
    return next(c["status"] for c in res["checks"] if c["n"] == n)


# ---------------------------------------------------------------- basics

def test_a_healthy_company_passes_everything():
    r = run(good())
    assert r["verdict"] == "passes" and not r["failed"]


def test_no_data_is_not_a_pass():
    r = run([])
    assert r["verdict"] == "no data" and r["checks"] == []


# ---------------------------------------------------------------- the seven

def test_weak_roe_excludes():
    assert 1 in run(good(net_income=20.0, equity=1000.0))["failed"]


def test_negative_free_cash_flow_excludes():
    assert 2 in run(good(free_cf=-50.0))["failed"]


def test_thin_interest_coverage_excludes():
    assert 3 in run(good(ebit=10.0, interest_expense=-10.0))["failed"]


def test_low_gross_margin_excludes():
    # Kept below every exemption threshold so nothing waives it.
    r = run(good(gross_profit=100.0, net_income=20.0, equity=1000.0, operating_cf=15.0))
    assert 4 in r["failed"]


def test_poor_cash_conversion_excludes():
    assert 5 in run(good(operating_cf=30.0))["failed"]


def test_heavy_dilution_is_flagged():
    rows = [year(2026, shares=1500.0)] + [year(2025 - i) for i in range(3)]
    assert 7 in run(rows)["failed"]


# ---------------------------------------------------------------- missing data

def test_missing_inputs_are_skipped_not_failed():
    """Better to let a weak company through than wrongly exclude a strong one — the
    source's own principle. A blank must never read as a zero."""
    r = run(good(gross_profit=None))
    assert status(r, 4) == "skipped"
    assert 4 not in r["failed"]


def test_zero_denominator_does_not_become_a_verdict():
    # Dividing by zero equity is undefined, not infinitely good or bad.
    r = run(good(equity=0.0))
    assert status(r, 1) == "skipped"


# ---------------------------------------------------------------- financials

def test_banks_skip_the_margin_tests():
    """yfinance reports grossMargins 0.0 for banks — a blank in the costume of a
    measurement. Judged literally it excludes HDFCBANK for a metric banks don't report."""
    rows = good(gross_profit=None, ebit=None)
    r = run(rows, sector="Banks")
    assert status(r, 4) == "skipped" and status(r, 3) == "skipped"
    assert r["verdict"] == "passes"


def test_a_bank_is_still_judged_on_the_tests_that_do_apply():
    r = run(good(gross_profit=None, ebit=None, free_cf=-10.0), sector="Banks")
    assert 2 in r["failed"]


# ---------------------------------------------------------------- M&A

def test_share_growth_alone_is_review_not_exclusion():
    """HDFCBANK's 37.9% share growth is the 2023 HDFC Ltd merger. The source excludes
    M&A-driven issuance; statements cannot distinguish it, so a human decides."""
    rows = [year(2026, shares=1500.0)] + [year(2025 - i) for i in range(3)]
    r = run(rows)
    assert r["verdict"] == "review" and r["failed"] == [7]
    assert "merger" in next(c["why"] for c in r["checks"] if c["n"] == 7)


def test_share_growth_plus_another_failure_is_a_real_exclusion():
    rows = [year(2026, shares=1500.0, free_cf=-10.0)] + \
           [year(2025 - i, free_cf=-10.0) for i in range(3)]
    assert run(rows)["verdict"] == "excluded"


# ---------------------------------------------------------------- exemptions

def test_exemptions_are_only_reported_when_they_waive_something():
    """TCS passes all seven tests; reporting it as being in a 'strategic investment
    phase' was simply wrong, and noise on every healthy company."""
    assert run(good())["exemptions"] == []


def test_high_turnover_exemption_rescues_a_costco_shaped_company():
    # Thin margins, but excellent capital efficiency and cash conversion.
    rows = good(gross_profit=120.0, net_income=25.0, equity=100.0, operating_cf=40.0)
    r = run(rows)
    assert status(r, 4) == "exempt"
    assert any(e["rule"] == "C" for e in r["exemptions"])


# ---------------------------------------------------------------- confidence

def test_thin_history_lowers_confidence():
    assert run(good(n=3))["confidence"] == "low"
    assert run(good(n=5))["confidence"] == "normal"


def test_confidence_drops_when_too_few_tests_could_be_scored():
    rows = good(gross_profit=None, ebit=None, operating_cf=None, free_cf=None)
    assert run(rows)["confidence"] == "low"


def test_years_is_reported_so_a_short_average_is_visible():
    # avg ROE over 4 years is not the source's 10-year test, and must not pretend to be.
    r = run(good(n=4))
    assert r["years"] == 4
    assert "4y" in next(c["name"] for c in r["checks"] if c["n"] == 1)


# ---------------------------------------------------------------- strength & grade

def test_clearing_a_threshold_by_more_scores_higher():
    weak = run(good(net_income=45.0, equity=500.0))     # ROE 9%, just over the 8% bar
    strong = run(good(net_income=200.0, equity=500.0))  # ROE 40%
    assert strong["strength"] > weak["strength"]


def test_one_spectacular_metric_cannot_carry_a_company():
    """Hindustan Zinc's 68% ROE is 8.5x the bar. Uncapped it would swamp six ordinary
    scores and make the grade a single-metric ranking."""
    absurd = run(good(net_income=5000.0, equity=100.0))
    for c in absurd["checks"]:
        if c["headroom"] is not None:
            assert c["headroom"] <= quality.HEADROOM_CAP


def test_share_growth_headroom_rewards_less_dilution():
    """Criterion 7 is inverted — lower is better — so the headroom must be too."""
    buyback = [year(2026, shares=900.0)] + [year(2025 - i) for i in range(3)]
    flat = good()
    h_buyback = next(c["headroom"] for c in run(buyback)["checks"] if c["n"] == 7)
    h_flat = next(c["headroom"] for c in run(flat)["checks"] if c["n"] == 7)
    assert h_buyback > h_flat


def test_a_failing_company_gets_no_grade():
    # Grading something the screen excluded would imply it is merely a weaker buy.
    r = run(good(free_cf=-50.0))
    assert r["verdict"] == "excluded" and r["grade"] is None


def test_grades_actually_discriminate():
    """Bands are quartiles of the passing set. The first attempt used 2.0/1.4/1.0 and
    gave 74 of 76 companies an A."""
    assert [g for _, g in quality.GRADE_BANDS] == ["A", "B", "C"]
    lo = [t for t, _ in quality.GRADE_BANDS]
    assert lo == sorted(lo, reverse=True)          # bands descend
    assert lo[0] < quality.HEADROOM_CAP            # an A must be reachable


# ------------------------------------------------- screen(): the universe-wide join

def test_screen_skips_symbols_with_no_statements():
    """Absent, not present-with-a-null-verdict. The screener has to be able to tell
    'this company fails the tests' from 'nobody ever fetched its statements'."""
    syms = [{"symbol": "A"}, {"symbol": "B"}]
    out = quality.screen(syms, {"A": good()}, {})
    assert set(out) == {"A"}


def test_screen_applies_the_sector_exemptions():
    """A bank must be recognised as one here too. Routed without its sector group it
    would be judged on gross margin, which is the exact HDFCBANK failure the module
    exists to avoid."""
    banky = good(gross_profit=None, net_income=10.0, revenue=1000.0)
    syms = [{"symbol": "BANK"}]
    plain = quality.screen(syms, {"BANK": banky}, {})["BANK"]
    bank = quality.screen(syms, {"BANK": banky}, {"BANK": "Banks"})["BANK"]
    assert bank["is_financial"] and not plain["is_financial"]
    assert 6 in plain["failed"] and 6 not in bank["failed"]


def test_screen_preserves_universe_order():
    syms = [{"symbol": s} for s in ("Z", "M", "A")]
    hist = {s["symbol"]: good() for s in syms}
    assert list(quality.screen(syms, hist, {})) == ["Z", "M", "A"]


def test_summary_drops_the_checks():
    """The screener shows one row per symbol; seven nested objects each would be
    unreadable and would triple the payload."""
    s = quality.summary(run(good()))
    assert set(s) == {"verdict", "grade", "strength", "years", "confidence"}
    assert s["verdict"] == "passes"


def test_grade_order_is_best_first():
    """min_grade filters with `>` against this, so A must be the smallest number and
    every band in GRADE_BANDS must be orderable."""
    assert quality.GRADE_ORDER["A"] == 0
    order = [quality.GRADE_ORDER[g] for _, g in quality.GRADE_BANDS]
    assert order == sorted(order)
    assert set(g for _, g in quality.GRADE_BANDS) | {"D"} == set(quality.GRADE_ORDER)
