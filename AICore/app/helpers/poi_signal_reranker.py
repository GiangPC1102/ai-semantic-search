"""Rerank POI vector hits using DB columns mapped from ranking signals."""

from __future__ import annotations

from typing import Any

from prisma.models import Poi

from app.schemas.signal_ranking import RankingSignalItem, RankingSignalType

RERANKABLE_SIGNALS: frozenset[RankingSignalType] = frozenset(
    {
        RankingSignalType.PRICE,
        RankingSignalType.RATING,
        RankingSignalType.POPULARITY,
        RankingSignalType.REVIEW,
    }
)


def extract_rerank_signals(
    signals: list[RankingSignalItem],
) -> list[RankingSignalItem]:
    """Return rerankable signals sorted by confidence (highest first)."""
    candidates = [
        item
        for item in signals
        if item.signal in RERANKABLE_SIGNALS
    ]
    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def rerank_poi_hits_by_signals(
    poi_hits: list[dict[str, Any]],
    poi_by_id: dict[str, Poi],
    signals: list[RankingSignalItem],
) -> list[dict[str, Any]]:
    """Rerank POI search hits before attribute intersection.

    Only runs when at least one of price/rating/popularity/review is present.
    Sort keys follow signal confidence (desc), then vector score as tiebreaker.

    Column mapping:
        - price → price_level (lower = better, e.g. cheap)
        - rating → rating (higher = better)
        - popularity → popularity_score (higher = better)
        - review → review_count (higher = better)
    """
    rerank_signals = extract_rerank_signals(signals)
    if not rerank_signals:
        return poi_hits

    return sorted(
        poi_hits,
        key=lambda hit: _build_sort_key(hit, poi_by_id, rerank_signals),
        reverse=True,
    )


def _build_sort_key(
    hit: dict[str, Any],
    poi_by_id: dict[str, Poi],
    rerank_signals: list[RankingSignalItem],
) -> tuple[float, ...]:
    """Higher tuple values rank earlier (reverse=True sort)."""
    poi_id = hit.get("poi_id")
    poi = poi_by_id.get(poi_id) if poi_id else None

    keys: list[float] = [
        _signal_sort_value(poi, signal) for signal in rerank_signals
    ]
    keys.append(float(hit.get("score") or float("-inf")))
    return tuple(keys)


def _signal_sort_value(
    poi: Poi | None,
    signal: RankingSignalType,
) -> float:
    """Normalize a POI field into a sortable score (higher = better rank)."""
    if poi is None:
        return float("-inf")

    if signal == RankingSignalType.PRICE:
        price_level = _parse_numeric(poi.priceLevel)
        if price_level is None:
            return float("-inf")
        # Lower price_level is better for typical "giá rẻ" intent.
        return -price_level

    if signal == RankingSignalType.RATING:
        return float(poi.rating) if poi.rating is not None else float("-inf")

    if signal == RankingSignalType.POPULARITY:
        return (
            float(poi.popularityScore)
            if poi.popularityScore is not None
            else float("-inf")
        )

    if signal == RankingSignalType.REVIEW:
        return (
            float(poi.reviewCount)
            if poi.reviewCount is not None
            else float("-inf")
        )

    return float("-inf")


def _parse_numeric(value: Any) -> float | None:
    """Parse POI scalar fields that may be stored as string or number."""
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
