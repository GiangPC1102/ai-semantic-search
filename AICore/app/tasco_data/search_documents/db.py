from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import Poi, PoiSearchDocument


def save_pois_text(session: Session, updates: list[dict]) -> int:
    if not updates:
        return 0

    for row in updates:
        stmt = (
            update(Poi)
            .where(Poi.poi_id == row["poi_id"])
            .values(semantic_text=row["semantic_text"], keyword_text=row["keyword_text"])
        )
        session.execute(stmt)

    return len(updates)


def upsert_search_documents(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    stmt = insert(PoiSearchDocument).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["doc_id"],
        set_={
            "content": stmt.excluded.content,
            "content_norm": stmt.excluded.content_norm,
        },
    )
    session.execute(stmt)
    return len(rows)
