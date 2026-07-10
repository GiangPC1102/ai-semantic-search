from app.database.models import Poi, PoiSignal


def build_semantic_text(poi: Poi, signals: list[PoiSignal]) -> str:
    parts = [poi.poi_name]

    if poi.brand:
        parts.append(poi.brand)
    if poi.category:
        parts.append(poi.category)
    if poi.sub_category:
        parts.append(poi.sub_category)

    location = ", ".join(filter(None, [poi.address, poi.district, poi.city]))
    if location:
        parts.append(location)

    if poi.description:
        parts.append(poi.description)

    signal_names = [s.signal_name for s in signals if s.signal_name]
    if signal_names:
        parts.append(", ".join(signal_names))

    summary = (poi.enrichment_json or {}).get("semantic_summary")
    if summary:
        parts.append(summary)

    return "\n".join(parts)


def build_keyword_text(poi: Poi, signals: list[PoiSignal]) -> str:
    fields = [
        poi.poi_name_norm,
        poi.brand_norm,
        poi.category_norm,
        poi.sub_category_norm,
        poi.city_norm,
        poi.district_norm,
        poi.address_norm,
    ]
    signal_norms = [s.signal_norm for s in signals]
    tokens = [f for f in fields if f] + signal_norms
    return " ".join(tokens)
