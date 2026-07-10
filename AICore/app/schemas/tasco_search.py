"""Schemas for Tasco search orchestration API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.signal_ranking import HardFilters, RankingSignalItem
from app.schemas.vector_search import VectorSearchHit


class TascoSearchRequest(BaseModel):
    """Request body for end-to-end Tasco search."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language POI search query",
        examples=["quán cafe yên tĩnh có wifi ở Quận 1"],
    )
    poi_top_k: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="POI vector search top_k; defaults to TASCO_POI_TOP_K",
    )
    attribute_top_k: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Attribute vector search top_k; defaults to TASCO_ATTRIBUTE_TOP_K",
    )


class TascoSearchItem(BaseModel):
    """One final POI hit after attribute intersection."""

    poi_id: str | None = None
    vector_id: str
    name: str | None = None
    text: str | None = None
    score: float | None = None
    matched_attribute_count: int = Field(
        default=0,
        description="Number of attributes overlapping attribute search hits",
    )
    matched_attribute_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class TascoSearchResponse(BaseModel):
    """Tasco search pipeline response."""

    original_query: str
    normalized_query: str
    hard_filters: HardFilters
    ranking_signals: list[RankingSignalItem]
    hard_filtered_poi_count: int
    poi_hits_count: int
    attribute_hits: list[VectorSearchHit]
    count: int
    items: list[TascoSearchItem]
