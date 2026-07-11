"""Schemas for Tasco search orchestration API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
        ge=10,
        le=100,
        description="POI vector search top_k; defaults to TASCO_POI_TOP_K",
    )
    attribute_top_k: int | None = Field(
        default=None,
        ge=5,
        le=100,
        description="Attribute vector search top_k; defaults to TASCO_ATTRIBUTE_TOP_K",
    )
    is_filter_attribute: bool = Field(
        default=False,
        description=(
            "When true, run attribute hybrid search and intersect POI hits with "
            "matched attributes. When false (default), skip attribute search and "
            "attribute filtering entirely."
        ),
    )


class PoiDetail(BaseModel):
    """Full POI row (plus brand summary) reused from hard-filter cache."""

    id: str
    name: str
    brand_id: str | None = None
    brand_name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    rating: float | None = None
    review_count: int | None = None
    popularity_score: float | None = None
    price_level: str | None = None
    open_hours: Any | None = None
    description: str | None = None
    vector_id: str | None = None


class SearchExplain(BaseModel):
    """Per-POI explanation of why this item matched the query."""

    hard_attributes: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Hard-filter fields this POI satisfies. ``subcategory`` is omitted "
            "when the filter rolled back to category-only."
        ),
    )
    ranking_signals: list[str] = Field(
        default_factory=list,
        description=(
            "Localized ranking-signal labels "
            "(EN → signal_name, VI/mixed → vietnam_name)"
        ),
    )
    attributes: list[str] = Field(
        default_factory=list,
        description=(
            "Localized labels of search-matched attributes that this POI has "
            "(EN → english_name, VI/mixed → attribute_name)"
        ),
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
    attributes: list[str] = Field(
        default_factory=list,
        description=(
            "Localized attribute names linked to this POI via poi_attributes "
            "(EN → english_name, VI/mixed → attribute_name)"
        ),
    )
    explain: SearchExplain = Field(
        default_factory=SearchExplain,
        description="Per-POI explanation (hard filters / signals / matched attrs)",
    )
    payload: dict[str, Any] = Field(default_factory=dict)
    poi: PoiDetail | None = Field(
        default=None,
        description="Full POI attributes from hard-filter cache (no extra DB query)",
    )


class TascoSearchResponse(BaseModel):
    """Tasco search pipeline response — lean top-level; detail lives in items."""

    original_query: str
    normalized_query: str
    hard_filtered_poi_count: int
    poi_hits_count: int
    count: int
    items: list[TascoSearchItem]
