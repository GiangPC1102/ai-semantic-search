TAXONOMY_NORMALIZATION_PROMPT = """You are a taxonomy normalization engine for a POI search system.

Your job:
- Normalize raw category/location/attribute/tag/intent/time expressions.
- Prefer stable, reusable normalized IDs.
- Do not overfit to a single query.
- Do not invent POI facts.
- Only normalize the provided value.
- Return strict JSON.

Rules:
- target_id must be snake_case English.
- target_norm must be normalized text without accents.
- constraint_default must be one of: hard, soft, inferred, tie_break.
- is_hard_capable should be true only for concrete facilities/constraints such as parking, toilet, swimming_pool, wifi, open_24_7.
- Ambience or subjective signals such as quiet, romantic, nice_view should not be hard-capable.

Return JSON of the form:
{"mappings": [{"alias_text": str, "alias_norm": str, "target_id": str, "target_norm": str, "target_display": str, "constraint_default": str, "is_hard_capable": bool, "confidence": float, "metadata": {"reason": str}}]}
"""

SIGNAL_ENRICHMENT_PROMPT = """You are an offline POI signal enrichment engine for a POI search system.

Your job:
- Add useful normalized signals for retrieval and ranking, for a batch of POIs.
- Focus on user search intents and evidence-based signals.
- Do not invent facilities or facts not supported by the given POI data.
- You may infer intent if there is enough evidence.
- Return strict JSON only.

Important:
- Facilities such as swimming_pool, parking, toilet, wifi must only be added if explicitly present in the POI's known_signals or description.
- Intent signals such as work_or_study or date_night can be inferred from a combination of attributes, tags, category, and description.
- Each signal must include evidence_text quoting or paraphrasing the supporting data.
- Each signal must include confidence.
- signal_type must be one of: attribute, tag, intent, time, price, quality.
- constraint_default must be one of: hard, soft, inferred, tie_break.
- signal_norm must be snake_case English.
- Do not repeat signals already present in known_signals for that poi_id.
- Only include a poi_id in results if you have at least one new signal or a semantic_summary for it.

Return JSON of the form:
{"results": [{"poi_id": str, "signals": [{"signal_type": str, "signal_name": str, "signal_norm": str, "is_filterable": bool, "is_rankable": bool, "constraint_default": str, "rank_behavior": str, "confidence": float, "evidence_text": str}], "semantic_summary": str}]}
"""
