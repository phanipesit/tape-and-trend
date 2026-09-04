"""Quality screen: seven tests that exclude companies, rather than predict prices.

Adapted from the quality-screen skill in xbtlin/ai-berkshire (MIT). The methodology is
accounting, so it transfers to NSE unchanged; only the data plumbing differs.

Worth being clear about what this is and is not. Every other measurement in this app
reports an expectancy with a confidence interval, because swing outcomes resolve in
10-20 bars and can be scored. Quality investing resolves over years, and the cache holds
two. So this is a **lens, not a measured edge**: "passes seven quality tests" is a
defensible statement, "will outperform" is not, and nothing here claims the latter.

The design principle from the source is worth keeping verbatim: better to let a weak
company through than to wrongly exclude a strong one. Every rule below is therefore
skipped rather than failed when the data is missing.

TWO DEVIATIONS FROM THE SOURCE, both forced by what the data actually contains:

1. Average ROE is over ~5 years, not 10. Free yfinance does not go back further for
   Indian listings. `years` is reported on every result so a thin history is visible
   rather than averaged away.
2. Financials are exempted from the gross-margin and net-margin rules, not just the
   interest-coverage rule the source exempts them from. yfinance omits Gross Profit and
   EBIT for banks entirely and reports grossMargins as 0.0 -- a blank wearing the
   costume of a measurement. Judged literally it would exclude HDFCBANK, one of the
   highest-quality businesses in the universe, for a metric banks do not report.
"""
from __future__ import annotations

MIN_AVG_ROE = 0.08          # 1. capital efficiency
MIN_INTEREST_COVER = 2.0    # 3. solvency
MIN_GROSS_MARGIN = 0.15     # 4. pricing power
MIN_OCF_TO_NI = 0.7         # 5. earnings quality
MIN_NET_MARGIN = 0.05       # 6. resilience
MAX_SHARE_GROWTH = 0.20     # 7. dilution

# Exemption thresholds, from the source's three carve-outs.
EXEMPT_GROSS_MARGIN = 0.30
EXEMPT_HIGH_ROE = 0.20

# sector_group() labels whose statements make margin tests meaningless.
FINANCIAL_GROUPS = {"Banks", "Financial Services"}


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _ratio(num, den):
    """None unless both sides are real and the denominator is usable. A zero
    denominator is undefined, not infinite, and must not become a pass or a fail."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def evaluate(symbol: str, rows: list[dict], sector_group: str | None = None) -> dict:
    """Run the seven tests over annual statements, newest first.

    Each check is pass / fail / skipped. `skipped` means the inputs were not reported,
    and never counts against the company.
    """
    if not rows:
        return {"symbol": symbol, "years": 0, "verdict": "no data",
                "checks": [], "failed": [], "exemptions": []}

    is_financial = sector_group in FINANCIAL_GROUPS
    years = len(rows)
    newest, oldest = rows[0], rows[-1]

    roes = [_ratio(r.get("net_income"), r.get("equity")) for r in rows]
    avg_roe = _mean(roes)
    gross_margins = [_ratio(r.get("gross_profit"), r.get("revenue")) for r in rows]
    avg_gross = _mean(gross_margins)
    net_margins = [_ratio(r.get("net_income"), r.get("revenue")) for r in rows]
    avg_net = _mean(net_margins)
    cum_fcf = _mean([r.get("free_cf") for r in rows])
    ocf_ni = _mean([_ratio(r.get("operating_cf"), r.get("net_income")) for r in rows])
    cover = _mean([_ratio(r.get("ebit"), abs(r["interest_expense"]))
                   for r in rows if r.get("interest_expense")])
    share_growth = _ratio(
        (newest.get("shares") or 0) - (oldest.get("shares") or 0), oldest.get("shares"))

    # --- exemptions ----------------------------------------------------------------
    # Availability only. Which ones were actually *used* is recorded during the checks,
    # because listing an exemption that waived nothing is noise: TCS passes all seven
    # tests and reporting it as being in a "strategic investment phase" is simply wrong.
    #
    # The source's exemption A also requires the company to have been listed under ten
    # years. There is no listing date in our data, and using "we hold under ten years of
    # statements" as a proxy makes it true for every company in the universe -- which is
    # how TCS, listed 2004, got tagged as an early-stage business. Without a real
    # listing date the condition cannot be evaluated, so A is not offered at all rather
    # than offered wrongly.
    available = {}
    if (avg_gross or 0) > EXEMPT_GROSS_MARGIN and (net_margins[0] or 0) >= MIN_NET_MARGIN:
        available["B"] = ("deliberately thin net margin — pricing power intact, latest "
                          "year already above the threshold")
    if (avg_roe or 0) > EXEMPT_HIGH_ROE and (ocf_ni or 0) > 1.0:
        available["C"] = ("high-turnover model — low margins but excellent capital "
                          "efficiency and cash conversion")
    if is_financial:
        available["F"] = ("financial — margin and interest-coverage tests do not apply "
                          "to a bank's income statement")
    used: set[str] = set()

    def check(n, name, value, ok, exempt_by=(), fail_note=""):
        if value is None:
            return {"n": n, "name": name, "value": None, "status": "skipped",
                    "why": "not reported"}
        hit = set(available) & set(exempt_by)
        if not ok and hit:
            used.update(hit)
            return {"n": n, "name": name, "value": round(value, 4),
                    "status": "exempt", "why": f"exemption {'/'.join(sorted(hit))}"}
        return {"n": n, "name": name, "value": round(value, 4),
                "status": "pass" if ok else "fail",
                "why": "" if ok else fail_note}

    checks = [
        check(1, f"avg ROE ({years}y)", avg_roe, (avg_roe or 0) >= MIN_AVG_ROE, ("A",)),
        check(2, "cumulative free cash flow", cum_fcf, (cum_fcf or 0) > 0),
        check(3, "interest coverage", cover,
              (cover or 0) >= MIN_INTEREST_COVER, ("F",)),
        check(4, "gross margin", None if is_financial else avg_gross,
              (avg_gross or 0) >= MIN_GROSS_MARGIN, ("C", "F")),
        check(5, "operating CF / net income", ocf_ni, (ocf_ni or 0) >= MIN_OCF_TO_NI),
        check(6, "net margin", None if is_financial else avg_net,
              (avg_net or 0) >= MIN_NET_MARGIN, ("B", "C", "F")),
        # The source qualifies this one as "> 20%, for non-M&A reasons". A merger
        # issues shares without diluting anyone's economic stake, and nothing in the
        # statements distinguishes the two. Dropping that qualifier excluded HDFCBANK
        # on the 2023 HDFC Ltd merger — precisely the wrongly-killed good company the
        # methodology exists to avoid. It cannot be automated, so it is surfaced for a
        # human instead of decided badly.
        check(7, "share count growth", share_growth,
              (share_growth or 0) <= MAX_SHARE_GROWTH,
              fail_note="check for a merger or acquisition — the rule excludes "
                        "M&A-driven issuance, which the statements cannot distinguish"),
    ]

    failed = [c["n"] for c in checks if c["status"] == "fail"]
    scored = [c for c in checks if c["status"] in ("pass", "fail", "exempt")]

    # A company clean on every test except share count is the classic merger case, so
    # it is held for review rather than excluded outright.
    if failed == [7]:
        verdict = "review"
    elif failed:
        verdict = "excluded"
    else:
        verdict = "passes"

    return {
        "symbol": symbol, "years": years,
        "sector_group": sector_group, "is_financial": is_financial,
        "checks": checks, "failed": failed,
        "passed": len(scored) - len(failed), "scored": len(scored),
        "skipped": [c["n"] for c in checks if c["status"] == "skipped"],
        "exemptions": [{"rule": r, "why": available[r]} for r in sorted(used)],
        "verdict": verdict,
        # A clean pass on three of seven tests is not the same as a clean pass on
        # seven, and the caller must be able to tell the difference.
        "confidence": "low" if len(scored) < 5 or years < 4 else "normal",
    }
