from app.tasco_data.stages.s2_normalize import normalize_text
from app.tasco_data.taxonomy.resolver import AliasCache, resolve

# alias_type -> row fields that feed it. "category"/"location" use single
# already-normalized fields; "attribute"/"tag" use raw semicolon-split lists
# that still need per-item normalization.
_SINGLE_VALUE_FIELDS = {
    "category": ["category_norm"],
    "location": ["city_norm", "district_norm"],
}
_LIST_VALUE_FIELDS = {
    "attribute": "attributes_raw",
    "tag": "tags_raw",
}


def collect_unknowns(rows: list[dict], cache: AliasCache) -> dict[str, dict[str, str]]:
    unknowns: dict[str, dict[str, str]] = {}

    for row in rows:
        for alias_type, fields in _SINGLE_VALUE_FIELDS.items():
            for field in fields:
                alias_norm = row.get(field)
                if not alias_norm:
                    continue
                if resolve(alias_type, alias_norm, cache) is None:
                    unknowns.setdefault(alias_type, {})[alias_norm] = alias_norm

        for alias_type, field in _LIST_VALUE_FIELDS.items():
            for raw_value in row.get(field) or []:
                alias_norm = normalize_text(raw_value)
                if not alias_norm:
                    continue
                if resolve(alias_type, alias_norm, cache) is None:
                    unknowns.setdefault(alias_type, {}).setdefault(alias_norm, raw_value)

    return unknowns
