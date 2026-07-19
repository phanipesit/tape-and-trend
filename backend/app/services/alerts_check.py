"""Evaluate active alerts against latest price / RSI and mark triggers."""
import logging
from ..db import q
from .data import quote
from .signals import latest_rsi

log = logging.getLogger(__name__)

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
                v = round(float(val), 2)
                q("""UPDATE alerts SET triggered_at=now(), triggered_value=:v WHERE id=:i""",
                  v=v, i=a["id"])
                fired.append({**a, "triggered_value": v})
                log.info("alert fired: %s %s %s (value %s)",
                         a["symbol"], a["condition"], a["threshold"], v)
        except Exception:
            log.warning("alert check failed for id=%s symbol=%s condition=%s",
                        a["id"], a["symbol"], a["condition"], exc_info=True)
            continue
    return fired
