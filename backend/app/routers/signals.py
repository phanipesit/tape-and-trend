from fastapi import APIRouter
from ..services import playbook
from ..services.data import all_symbols
from ..services.edge_stats import edge_book, rule_stats
from ..services.signals import analyse

router = APIRouter(prefix="/api", tags=["signals"])

@router.get("/signals")
def signals(market: str | None = None, triggered_only: bool = True):
    book, regimes = edge_book(), playbook.regimes()
    out = []
    for s in all_symbols(market):
        a = analyse(s["symbol"])
        if "error" in a or (triggered_only and not a["signals"]):
            continue
        a["market"] = s["market"]
        out.append(playbook.grade(a, book, regimes.get(s["market"])))
    return sorted(out, key=playbook.sort_key)

@router.get("/signals/desk")
def desk():
    """System expectancy, each market's regime, and which rules are live in it."""
    return playbook.desk(edge_book(), playbook.regimes(), rule_stats()["overall"])

@router.get("/signals/{symbol}")
def one(symbol: str):
    return analyse(symbol.upper())
