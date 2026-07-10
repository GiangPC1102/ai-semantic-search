from app.database.models import Poi, PoiSignal


def _signal_intent_content(poi: Poi, signals: list[PoiSignal]) -> str:
    parts = [poi.poi_name]

    intent_signals = [s for s in signals if s.signal_type == "intent"]
    other_signals = [s for s in signals if s.signal_type != "intent"]

    if intent_signals:
        intent_texts = [
            f"{s.signal_norm} ({s.evidence_text})" if s.evidence_text else s.signal_norm
            for s in intent_signals
        ]
        parts.append("Intents: " + ", ".join(intent_texts))

    if other_signals:
        parts.append("Signals: " + ", ".join(s.signal_norm for s in other_signals))

    return "\n".join(parts)


def _name_location_content(poi: Poi) -> str:
    parts = [poi.poi_name]
    if poi.brand:
        parts.append(poi.brand)

    location = ", ".join(filter(None, [poi.address, poi.district, poi.city]))
    if location:
        parts.append(location)

    return "\n".join(parts)


def build_search_documents(
    poi: Poi,
    signals: list[PoiSignal],
    semantic_text: str,
    keyword_text: str,
) -> list[dict]:
    signal_norms_text = " ".join(s.signal_norm for s in signals)

    return [
        {
            "doc_id": f"{poi.poi_id}::full_semantic",
            "poi_id": poi.poi_id,
            "doc_type": "full_semantic",
            "content": semantic_text,
            "content_norm": keyword_text,
        },
        {
            "doc_id": f"{poi.poi_id}::signal_intent",
            "poi_id": poi.poi_id,
            "doc_type": "signal_intent",
            "content": _signal_intent_content(poi, signals),
            "content_norm": signal_norms_text,
        },
        {
            "doc_id": f"{poi.poi_id}::name_location",
            "poi_id": poi.poi_id,
            "doc_type": "name_location",
            "content": _name_location_content(poi),
            "content_norm": " ".join(
                filter(
                    None,
                    [
                        poi.poi_name_norm,
                        poi.brand_norm,
                        poi.city_norm,
                        poi.district_norm,
                        poi.address_norm,
                    ],
                )
            ),
        },
    ]
