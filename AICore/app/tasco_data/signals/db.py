from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import Poi, PoiSignal


def upsert_poi_signals(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    stmt = insert(PoiSignal).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_poi_signal_unique")
    session.execute(stmt)
    return len(rows)


def save_enrichment_summaries(session: Session, summaries: dict[str, str]) -> int:
    if not summaries:
        return 0

    for poi_id, summary in summaries.items():
        stmt = (
            update(Poi)
            .where(Poi.poi_id == poi_id)
            .values(enrichment_json={"semantic_summary": summary})
        )
        session.execute(stmt)

    return len(summaries)
