import re
from decimal import Decimal
from typing import Optional

from app.tasco_data.stages.s2_normalize import normalize_text
from app.tasco_data.taxonomy.resolver import AliasCache, resolve

_NON_SNAKE = re.compile(r"[^a-z0-9]+")


def _to_snake(value: str) -> str:
    return _NON_SNAKE.sub("_", value).strip("_")


def _resolved_signal(poi_id: str, alias_type: str, alias_norm: str, evidence_text: Optional[str], cache: AliasCache) -> dict:
    target = resolve(alias_type, alias_norm, cache)
    if target:
        return {
            "poi_id": poi_id,
            "signal_type": alias_type,
            "signal_name": target.target_display or target.target_id,
            "signal_norm": target.target_id,
            "is_filterable": target.is_hard_capable,
            "is_rankable": True,
            "constraint_default": target.constraint_default,
            "rank_behavior": "boost",
            "confidence": Decimal("1.0"),
            "source": "rule_generated",
            "evidence_text": evidence_text,
        }
    return {
        "poi_id": poi_id,
        "signal_type": alias_type,
        "signal_name": evidence_text or alias_norm,
        "signal_norm": _to_snake(alias_norm),
        "is_filterable": False,
        "is_rankable": True,
        "constraint_default": "soft",
        "rank_behavior": "boost",
        "confidence": Decimal("1.0"),
        "source": "rule_generated",
        "evidence_text": evidence_text,
    }


def _rule_signal(poi_id: str, signal_type: str, signal_norm: str, signal_name: str, constraint_default: str, evidence_text: str) -> dict:
    return {
        "poi_id": poi_id,
        "signal_type": signal_type,
        "signal_name": signal_name,
        "signal_norm": signal_norm,
        "is_filterable": True,
        "is_rankable": True,
        "constraint_default": constraint_default,
        "rank_behavior": "boost",
        "confidence": Decimal("1.0"),
        "source": "rule_generated",
        "evidence_text": evidence_text,
    }


def generate_deterministic_base_signals(rows: list[dict], cache: AliasCache) -> list[dict]:
    signals: list[dict] = []

    for row in rows:
        poi_id = row["poi_id"]

        category_norm = row.get("category_norm")
        if category_norm:
            signals.append(_resolved_signal(poi_id, "category", category_norm, row.get("category"), cache))

        for norm_field, raw_field in (("city_norm", "city"), ("district_norm", "district")):
            value_norm = row.get(norm_field)
            if value_norm:
                signals.append(_resolved_signal(poi_id, "location", value_norm, row.get(raw_field), cache))

        for raw_value in row.get("attributes_raw") or []:
            alias_norm = normalize_text(raw_value)
            if alias_norm:
                signals.append(_resolved_signal(poi_id, "attribute", alias_norm, raw_value, cache))

        for raw_value in row.get("tags_raw") or []:
            alias_norm = normalize_text(raw_value)
            if alias_norm:
                signals.append(_resolved_signal(poi_id, "tag", alias_norm, raw_value, cache))

        if row.get("is_24_7"):
            signals.append(
                _rule_signal(poi_id, "time", "open_24_7", "Mo cua 24/7", "hard", row.get("opening_hours_raw") or "24/7")
            )

        rating = row.get("rating")
        if rating is not None and float(rating) >= 4.5:
            signals.append(_rule_signal(poi_id, "quality", "high_rating", "Danh gia cao", "inferred", f"rating={rating}"))

        price_level = row.get("price_level")
        if price_level is not None and price_level <= 2:
            signals.append(
                _rule_signal(poi_id, "price", "budget_friendly", "Gia binh dan", "inferred", f"price_level={price_level}")
            )

    return signals
