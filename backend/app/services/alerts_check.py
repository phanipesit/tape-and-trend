"""Evaluate active alerts against latest price / RSI and mark triggers."""
from ..db import q
from .data import quote
from .signals import latest_rsi

def check_all() -> list[dict]:
    fired = []
    active = q("SELECT * FROM alerts WHERE is_active AND triggered_at IS NULL")
    for a in active:
        try:
            cond, th = a["condition"], float(a["threshold"])
            if cond.startswith("price"):
                val = quote(a["symbol"])["price"]
            else:
                val = latest_rsi(a["symbol"])
            if val is None:
                continue
            hit = (cond.endswith("above") and val > th) or (cond.endswith("below") and val < th)
            if hit:
                q("""UPDATE alerts SET triggered_at=now(), triggered_value=:v WHERE id=:i""",
                  v=round(float(val), 2), i=a["id"])
                fired.append({**a, "triggered_value": round(float(val), 2)})
        except Exception:
            continue
    return fired
