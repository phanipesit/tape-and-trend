from sqlalchemy import create_engine, text
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def q(sql: str, **params):
    """Run a query, return list of dicts."""
    with engine.begin() as cx:
        rs = cx.execute(text(sql), params)
        if rs.returns_rows:
            return [dict(r._mapping) for r in rs]
        return []
