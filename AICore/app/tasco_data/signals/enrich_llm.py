import logging
import re
from typing import Iterable

from app.tasco_data.llm.litellm_service import LiteLLMService
from app.tasco_data.llm.prompts import SIGNAL_ENRICHMENT_PROMPT

logger = logging.getLogger(__name__)

_VALID_SIGNAL_TYPES = {"attribute", "tag", "intent", "time", "price", "quality"}
_VALID_CONSTRAINTS = {"hard", "soft", "inferred", "tie_break"}
_MIN_CONFIDENCE = 0.75
_SNAKE_NORM = re.compile(r"^[a-z][a-z0-9_]*$")


def _chunk(values: list, size: int) -> Iterable[list]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def validate_enriched_signals(poi_id: str, result_item: dict) -> list[dict]:
    accepted = []
    for signal in result_item.get("signals", []):
        signal_type = signal.get("signal_type")
        signal_norm = signal.get("signal_norm") or ""
        constraint_default = signal.get("constraint_default")
        confidence = signal.get("confidence", 0)
        evidence_text = signal.get("evidence_text")

        if signal_type not in _VALID_SIGNAL_TYPES:
            continue
        if not _SNAKE_NORM.match(signal_norm):
            continue
        if constraint_default not in _VALID_CONSTRAINTS:
            continue
        if confidence is None or confidence < _MIN_CONFIDENCE:
            continue
        if not evidence_text:
            continue

        accepted.append(
            {
                "poi_id": poi_id,
                "signal_type": signal_type,
                "signal_name": signal.get("signal_name") or signal_norm,
                "signal_norm": signal_norm,
                "is_filterable": bool(signal.get("is_filterable", False)),
                "is_rankable": bool(signal.get("is_rankable", True)),
                "constraint_default": constraint_default,
                "rank_behavior": signal.get("rank_behavior") or "boost",
                "confidence": confidence,
                "source": "llm_signal_enrichment",
                "evidence_text": evidence_text,
            }
        )

    return accepted


def enrich_pois_with_litellm(
    rows: list[dict],
    signals_by_poi: dict[str, list[dict]],
    intent_targets: list[str],
    llm: LiteLLMService,
    batch_size: int = 10,
) -> tuple[list[dict], dict[str, str]]:
    all_signals: list[dict] = []
    summaries: dict[str, str] = {}

    for batch in _chunk(rows, batch_size):
        payload = {
            "pois": [
                {
                    "poi_id": row["poi_id"],
                    "poi_name": row.get("poi_name"),
                    "category_norm": row.get("category_norm"),
                    "city_norm": row.get("city_norm"),
                    "district_norm": row.get("district_norm"),
                    "opening_hours_raw": row.get("opening_hours_raw"),
                    "rating": float(row["rating"]) if row.get("rating") is not None else None,
                    "price_level": row.get("price_level"),
                    "description": row.get("description"),
                    "known_signals": [
                        {
                            "signal_type": s["signal_type"],
                            "signal_norm": s["signal_norm"],
                            "evidence_text": s.get("evidence_text"),
                        }
                        for s in signals_by_poi.get(row["poi_id"], [])
                    ],
                }
                for row in batch
            ],
            "allowed_signal_types": sorted(_VALID_SIGNAL_TYPES),
            "existing_taxonomy_targets": intent_targets,
        }

        result = llm.complete_json(
            system_prompt=SIGNAL_ENRICHMENT_PROMPT,
            user_payload=payload,
        )

        for item in result.get("results", []):
            poi_id = item.get("poi_id")
            if not poi_id:
                continue

            all_signals.extend(validate_enriched_signals(poi_id, item))

            summary = item.get("semantic_summary")
            if summary:
                summaries[poi_id] = summary

    return all_signals, summaries
