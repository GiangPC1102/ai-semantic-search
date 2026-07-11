import re
import unicodedata
from typing import Optional

_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACE = re.compile(r"\s+")

_TEXT_FIELDS = [
    "poi_name",
    "brand",
    "category",
    "sub_category",
    "city",
    "district",
    "address",
    "description",
]


def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = value.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _NON_ALNUM_SPACE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text or None


def normalize_text_fields(item: dict) -> dict:
    normalized = dict(item)
    for field in _TEXT_FIELDS:
        normalized[f"{field}_norm"] = normalize_text(item.get(field))
    return normalized
