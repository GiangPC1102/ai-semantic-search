import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import TaxonomyAlias
from app.tasco_data.taxonomy.seed_data import MINIMAL_TAXONOMY_SEED

logger = logging.getLogger(__name__)


def seed_minimal_taxonomy_aliases(session: Session) -> int:
    rows = [
        {
            "alias_type": alias_type,
            "alias_text": alias_text,
            "alias_norm": alias_text,
            "target_id": target_id,
            "target_norm": target_id.replace("_", " "),
            "target_display": target_display,
            "constraint_default": constraint_default,
            "is_hard_capable": is_hard_capable,
            "source": "manual_seed",
        }
        for alias_type, alias_text, target_id, target_display, constraint_default, is_hard_capable in MINIMAL_TAXONOMY_SEED
    ]

    stmt = insert(TaxonomyAlias).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_taxonomy_alias_unique")
    session.execute(stmt)

    logger.info("Seeded %d minimal taxonomy aliases (idempotent)", len(rows))
    return len(rows)
