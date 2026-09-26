"""Bond yields. No DB, no network: FBIL files are built in memory, series are hand-made."""
import io
import zipfile
from datetime import date, timedelta

import pytest

from app.services import bonds


# ---------------------------------------------------------------- FBIL xlsx parsing

def xlsx(sheets: dict[str, list[list]]) -> bytes:
    """A minimal xlsx with the given sheets, strings shared the way Excel writes them."""
    shared: list[str] = []

    def cell(ref, v):
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        if v not in shared:
            shared.append(v)
        return f'<c r="{ref}" t="s"><v>{shared.index(v)}</v></c>'

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        entries, rels = [], []
        for i, (name, rows) in enumerate(sheets.items(), 1):
            body = "".join(
                f'<row r="{r}">' + "".join(cell(f"{'ABC'[c]}{r}", v) for c, v in enumerate(row)) + "</row>"
                for r, row in enumerate(rows, 1))
            z.writestr(f"xl/worksheets/sheet{i}.xml", f"<worksheet {ns}><sheetData>{body}</sheetData></worksheet>")
            entries.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>')
        z.writestr("xl/workbook.xml", f"<workbook {ns} {rns}><sheets>{''.join(entries)}</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", f"<Relationships>{''.join(rels)}</Relationships>")
        z.writestr("xl/sharedStrings.xml",
                   f"<sst {ns}>" + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
    return buf.getvalue()


PAR = [
    ["Financial Benchmarks India Private Ltd", "", ""],
    ["", "", ""],
    ["FBIL GSec Base/Par Yield", "", "25-Sep-2026"],
    ["", "", ""],
    ["Tenor (Year)", "YTM% p.a.(Semi-Annual)", "YTM % p.a.(Annualized)"],
    [0.25, 5.39, 5.46], [2, 6.32, 6.42], [10, 7.14, 7.27], [40, 7.67, 7.82],
]


def test_par_curve_is_read_by_sheet_name_not_position():
    """The G-Sec price sheet comes first in FBIL's file; order is theirs to change."""
    blob = xlsx({"G-Sec": [["ISIN", "Coupon"], ["IN0020230119", 7.33]], "Par Yield": PAR})
    d, pts = bonds.parse_par_curve(blob)
    assert d == date(2026, 9, 25)
    assert pts[0] == (0.25, 5.39, 5.46) and (10.0, 7.14, 7.27) in pts and len(pts) == 4


def test_header_rows_are_not_mistaken_for_tenors():
    _, pts = bonds.parse_par_curve(xlsx({"Par Yield": PAR}))
    assert all(t > 0 for t, _, _ in pts)


def test_missing_par_sheet_fails_loudly():
    with pytest.raises(ValueError, match="Par Yield"):
        bonds.parse_par_curve(xlsx({"G-Sec": [["x"]]}))


def test_undated_file_is_rejected():
    """The caller checks the file's own date against the one it asked for."""
    with pytest.raises(ValueError, match="date"):
        bonds.parse_par_curve(xlsx({"Par Yield": [["Tenor"], [10, 7.1, 7.2]]}))


# ---------------------------------------------------------------- summarise

D = date(2026, 9, 25)


def curve(y3m, y10, **extra):
    return {0.25: y3m, 10.0: y10, **extra}


def test_changes_are_basis_points_not_percent():
    s = {D - timedelta(days=1): curve(5.30, 7.08), D: curve(5.39, 7.14)}
    r = bonds.summarise(s, (0.25, 10), "t", today=D)
    ten = next(p for p in r["points"] if p["tenor"] == 10)
    assert ten["chg_bp"] == 6.0          # 7.08 -> 7.14, not "+0.85%"


def test_month_change_uses_a_curve_at_least_four_weeks_back():
    s = {D - timedelta(days=35): curve(5.2, 6.90), D - timedelta(days=10): curve(5.3, 7.0),
         D: curve(5.4, 7.14)}
    r = bonds.summarise(s, (10,), "t", today=D)
    assert r["points"][0]["chg_1m_bp"] == 24.0 and r["ten_year_1m"] == "rising"


def test_no_month_of_history_reports_none_rather_than_a_short_window():
    r = bonds.summarise({D: curve(5.4, 7.14)}, (10,), "t", today=D)
    assert r["points"][0]["chg_1m_bp"] is None and r["ten_year_1m"] is None


@pytest.mark.parametrize("y3m,y10,shape", [(5.39, 7.14, "normal"), (6.9, 7.14, "flat"),
                                           (5.4, 5.2, "inverted")])
def test_curve_shape_from_the_10y_3m_slope(y3m, y10, shape):
    assert bonds.summarise({D: curve(y3m, y10)}, (0.25, 10), "t", today=D)["curve"] == shape


def test_lag_is_reported_so_a_week_old_curve_never_passes_for_today():
    """FBIL's public archive trails by about a week."""
    r = bonds.summarise({D - timedelta(days=8): curve(5.3, 7.08)}, (10,), "t", today=D)
    assert r["lag_days"] == 8


def test_latest_date_is_the_newest_with_a_10y_point():
    """A US day where only one ticker refreshed must not become the as-of date."""
    s = {D - timedelta(days=1): curve(4.0, 5.1), D: {0.25: 4.1}}
    assert bonds.summarise(s, (10,), "t", today=D)["as_of"] == (D - timedelta(days=1)).isoformat()


def test_empty_series_is_none():
    assert bonds.summarise({}, (10,), "t") is None


# ---------------------------------------------------------------- read

def test_read_states_the_spread_and_each_curve():
    india = bonds.summarise({D: curve(5.39, 7.14)}, (0.25, 10), "t", today=D)
    us = bonds.summarise({D: curve(4.07, 5.18)}, (0.25, 10), "t", today=D)
    r = bonds.read(india, us, (D, 5.18))
    assert r["spread_10y_bp"] == 196.0 and r["spread_as_of"] == D.isoformat()
    assert "India curve normal" in r["verdict"] and "over US by 196bp" in r["verdict"]


def test_read_with_one_market_missing_still_reads():
    us = bonds.summarise({D: curve(5.4, 5.2)}, (0.25, 10), "t", today=D)
    r = bonds.read(None, us)
    assert r["spread_10y_bp"] is None and r["verdict"] == "US curve inverted"


def test_tenor_labels():
    assert [bonds.tenor_label(t) for t in (0.25, 0.5, 2, 10, 30)] == ["3M", "6M", "2Y", "10Y", "30Y"]


def test_spread_is_taken_on_indias_date_not_each_sides_latest():
    """FBIL trails a week; pairing its curve with today's Treasury close mixes two dates."""
    us = {D - timedelta(days=8): curve(4.0, 4.80), D: curve(4.07, 5.18)}
    india = bonds.summarise({D - timedelta(days=8): curve(5.33, 7.08)}, (0.25, 10), "t", today=D)
    matched = bonds.ten_year_on(us, D - timedelta(days=8))
    r = bonds.read(india, bonds.summarise(us, (0.25, 10), "t", today=D), matched)
    assert r["spread_10y_bp"] == 228.0          # 7.08 - 4.80, not 7.08 - 5.18


def test_ten_year_on_a_holiday_uses_the_prior_session():
    us = {D - timedelta(days=3): curve(4.0, 5.0)}
    assert bonds.ten_year_on(us, D) == (D - timedelta(days=3), 5.0)
    assert bonds.ten_year_on(us, D - timedelta(days=4)) is None
