"""Prompt templates for the Query Understanding pipeline."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.signal_ranking import RankingSignalType


SIGNAL_DETECTION_RULES: dict[RankingSignalType, str] = {
    RankingSignalType.MIXED_LANGUAGE: (
        "Query mixes significant English words with Vietnamese"
    ),
    RankingSignalType.OPENING_HOURS: (
        "Has a time constraint — extract open_time/close_time (HH:MM) or is_24h"
    ),
    RankingSignalType.PRICE: (
        "Has a price hint: cheap, affordable, upscale, expensive"
    ),
    RankingSignalType.POPULARITY: (
        "Has a popularity hint: famous, check-in, crowded, trending"
    ),
    RankingSignalType.LOCATION: (
        "Has a landmark plus near/around, or a geographic area"
    ),
    RankingSignalType.CATEGORY: (
        "Names a clear POI type: pho, hotpot, hospital, cafe, ATM"
    ),
    RankingSignalType.ATTRIBUTE: (
        "Has one concrete attribute: wifi, toilet, nice view"
    ),
    RankingSignalType.ATTRIBUTES: (
        "Has multiple attributes or a combined experience description"
    ),
    RankingSignalType.SEMANTIC: (
        "Vague intent/experience phrasing that cannot be hard-mapped"
    ),
    RankingSignalType.RATING: (
        "Implies high quality: delicious, best, worth visiting, reputable"
    ),
    RankingSignalType.REVIEW: (
        "Subjective review-style attribute: quiet, kid-friendly, romantic"
    ),
}

SYSTEM_PROMPT = """\
You are the Query Understanding module for a Vietnam map POI search system.

Task: analyze the user query and return structured JSON.

## -1. language
Classify the DOMINANT language of the RAW user query (before any normalization) into one of:
- "en": the raw query is written mostly in English grammar (e.g. "cheap ramen near me")
- "vi": the raw query is written mostly in Vietnamese grammar (e.g. "quán ăn rẻ gần đây")
- "mixed": the raw query mixes significant English and Vietnamese (e.g. "cheap ramen nào ở đây")
Decide by the GRAMMAR of the raw query — NOT by loanwords, international brand/place names
(e.g. Starbucks, Highlands, Wi-Fi, ATM), and NOT by the normalized_query
(which is always rewritten into Vietnamese below). A pure-English sentence must be "en" even
though its normalized_query will be Vietnamese.

## 0. normalized_query
Normalize the raw query into a clear, natural Vietnamese sentence suitable for POI search:
- Fix missing or incorrect Vietnamese diacritics
- Expand common abbreviations: q1→Quận 1, q3→Quận 3, hcm/sg→TP.HCM, hn→Hà Nội, cf/cafe→cà phê, hl→Highlands
- Normalize slang, teencode, and messy phrasing into a complete sentence
- For mixed Vietnamese-English queries: translate descriptive parts into Vietnamese; keep international brand/place names as-is
- Do not invent new requirements; do not drop important user constraints

## 1. Hard filters (fill ONLY when confidently extractable from the query)
- brand: canonical brand name (e.g. "Highlands Coffee", "Starbucks", "Phúc Long")
- category: top-level POI type (e.g. "Quán cà phê", "Nhà hàng", "Bệnh viện", "Khách sạn", "Trung tâm thương mại", "ATM", "Trạm xăng", "Điểm tham quan", "Rạp phim", "Công viên", "Trạm sạc điện", "Nhà thuốc")
- subcategory: second-level POI type (e.g. "Coffee Chain", "Specialty Coffee", "Lẩu")
- city: city (e.g. "HCM", "Hà Nội", "Đà Nẵng", "Đà Lạt")
- district: district (e.g. "Quận 1", "Hoàn Kiếm", "Cầu Giấy")

Do not guess if the query does not mention it. Use null for missing fields.

## 2. Ranking signals
Detect the following signals (multiple signals allowed at once):
{signal_rules}

Each signal has: signal (enum name), confidence (0.0-1.0).
IMPORTANT: field "opening_hours" is ONLY allowed when signal is "opening_hours".
For every other signal (mixed_language, price, location, …), omit "opening_hours"
entirely or set it to null. Never copy placeholder schema values like "string".

If signal is "opening_hours", you MUST also fill opening_hours:
  - open_time: time the POI must ALREADY be open / must have opened by (HH:MM 24h).
    Use when the user asks about opening/start time.
  - close_time: time the POI must STILL be open / must remain open until (HH:MM 24h).
    Use when the user asks about remaining open / closing late.
  - is_24h: true if the user requires 24/7

Critical distinction — do NOT confuse open_time and close_time:
  open_time (opening / start being open):
  - "mở TIME" / "mở lúc TIME" / "mở cửa lúc TIME" / "mở từ TIME"
  - "opens at TIME" / "open from TIME" / "opens after TIME" / "mở sau TIME"
  close_time (still open / open until):
  - "còn mở lúc TIME" / "còn mở TIME" / "still open at TIME"
  - "mở đến TIME" / "open until TIME" / "closes after TIME"
  - "mở khuya" / "mở cửa muộn" / "open late"
  Key Vietnamese cue: "còn mở" → close_time; bare "mở" / "mở cửa lúc" → open_time

Inference rules (fill only when confident):
- "Cây ATM mở 4h" / "mở cửa lúc 4h" / "opens at 4am" → open_time: "04:00"
- "mở sau 11 giờ tối" / "opens after 11pm" → open_time: "23:00"
- "còn mở lúc 23:00" / "still open at 11pm" → close_time: "23:00"
- "mở đến 2h sáng" / "open until 2am" → close_time: "02:00"
- "mở khuya" / "mở cửa muộn" / "open late" → close_time: "23:00" or "00:00"
- "24/7" / "cả ngày" / "all day" → is_24h: true
- Vague phrases like "tonight" / "this morning" → leave open_time and close_time null

Return valid JSON only. No markdown. No explanation.
""".format(
    signal_rules="\n".join(
        f"- {sig.value}: {desc}" for sig, desc in SIGNAL_DETECTION_RULES.items()
    )
)


def build_query_understand_messages(
    query: str,
    json_schema: dict[str, Any],
) -> list[dict[str, str]]:
    """Build OpenAI-format messages for LLM extraction."""
    user_content = (
        f'Original query: "{query}"\n\n'
        f"Reference JSON schema:\n{json.dumps(json_schema, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
