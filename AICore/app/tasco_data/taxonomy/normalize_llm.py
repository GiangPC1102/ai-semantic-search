import logging
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import TaxonomyAlias
from app.tasco_data.llm.litellm_service import LiteLLMService
from app.tasco_data.llm.prompts import TAXONOMY_NORMALIZATION_PROMPT

logger = logging.getLogger(__name__)

_VALID_CONSTRAINTS = {"hard", "soft", "inferred", "tie_break"}
_MIN_CONFIDENCE = 0.75


def _chunk(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def validate_taxonomy_mappings(result: dict) -> list[dict]:
    accepted = []
    for mapping in result.get("mappings", []):
        target_id = mapping.get("target_id")
        alias_norm = mapping.get("alias_norm")
        constraint_default = mapping.get("constraint_default")
        confidence = mapping.get("confidence", 0)

        if not alias_norm or not target_id:
            continue
        if constraint_default not in _VALID_CONSTRAINTS:
            continue
        if confidence is None or confidence < _MIN_CONFIDENCE:
            continue

        accepted.append(mapping)

    return accepted


def normalize_unknowns_with_litellm(
    unknowns: dict[str, dict[str, str]],
    llm: LiteLLMService,
    existing_targets_by_type: dict[str, list[str]],
    batch_size: int = 20,
) -> list[dict]:
    all_aliases = []

    for alias_type, norm_to_text in unknowns.items():
        alias_texts = sorted(set(norm_to_text.values()))

        for batch in _chunk(alias_texts, batch_size):
            payload = {
                "alias_type": alias_type,
                "values": batch,
                "existing_targets": existing_targets_by_type.get(alias_type, []),
            }

            result = llm.complete_json(
                system_prompt=TAXONOMY_NORMALIZATION_PROMPT,
                user_payload=payload,
            )

            for mapping in validate_taxonomy_mappings(result):
                mapping["alias_type"] = alias_type
                all_aliases.append(mapping)

    return all_aliases


def save_taxonomy_aliases(session: Session, mappings: list[dict]) -> int:
    if not mappings:
        return 0

    rows = [
        {
            "alias_type": m["alias_type"],
            "alias_text": m["alias_text"],
            "alias_norm": m["alias_norm"],
            "target_id": m["target_id"],
            "target_norm": m["target_norm"],
            "target_display": m.get("target_display"),
            "constraint_default": m["constraint_default"],
            "is_hard_capable": m.get("is_hard_capable", False),
            "confidence": m.get("confidence"),
            "metadata_json": m.get("metadata"),
            "source": "llm_taxonomy_normalization",
        }
        for m in mappings
    ]

    stmt = insert(TaxonomyAlias).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_taxonomy_alias_unique")
    session.execute(stmt)

    logger.info("Saved %d LLM-normalized taxonomy aliases", len(rows))
    return len(rows)
