from decimal import Decimal, InvalidOperation
from typing import Optional


def _clean_str(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value, places: int = 2) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(round(float(value), places)))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _to_list(value) -> list[str]:
    text = _clean_str(value)
    if not text:
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def normalize_schema(row: dict) -> dict:
    opening_hours_raw = _clean_str(row.get("opening_hours"))

    return {
        "poi_id": _clean_str(row.get("poi_id")),
        "poi_name": _clean_str(row.get("poi_name")),
        "brand": _clean_str(row.get("brand")),
        "category": _clean_str(row.get("category")),
        "sub_category": _clean_str(row.get("sub_category")),
        "city": _clean_str(row.get("city")),
        "district": _clean_str(row.get("district")),
        "address": _clean_str(row.get("address")),
        "latitude": _to_float(row.get("latitude")),
        "longitude": _to_float(row.get("longitude")),
        "rating": _to_decimal(row.get("rating")),
        "review_count": _to_int(row.get("review_count")),
        "popularity_score": _to_int(row.get("popularity_score")),
        "price_level": _to_int(row.get("price_level")),
        "opening_hours_raw": opening_hours_raw,
        "is_24_7": opening_hours_raw == "24/7",
        "description": _clean_str(row.get("description")),
        "attributes_raw": _to_list(row.get("attributes")),
        "tags_raw": _to_list(row.get("tags")),
    }
