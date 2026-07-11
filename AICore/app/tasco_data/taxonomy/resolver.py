from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import TaxonomyAlias


@dataclass(frozen=True)
class AliasTarget:
    target_id: str
    target_norm: str
    target_display: Optional[str]
    constraint_default: str
    is_hard_capable: bool


AliasCache = dict[tuple[str, str], AliasTarget]


def load_alias_cache(session: Session) -> AliasCache:
    rows = session.execute(select(TaxonomyAlias)).scalars().all()
    return {
        (row.alias_type, row.alias_norm): AliasTarget(
            target_id=row.target_id,
            target_norm=row.target_norm,
            target_display=row.target_display,
            constraint_default=row.constraint_default,
            is_hard_capable=row.is_hard_capable,
        )
        for row in rows
    }


def resolve(alias_type: str, alias_norm: str, cache: AliasCache) -> Optional[AliasTarget]:
    if not alias_norm:
        return None
    return cache.get((alias_type, alias_norm))
