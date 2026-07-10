"""Schema request/response cho API lọc POI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.signal_ranking import HardFilters, RankingSignalItem


class PoiFilterRequest(BaseModel):
    """Request body lọc POI theo hard-filter và ranking signals."""

    hard_filters: HardFilters = Field(default_factory=HardFilters)
    ranking_signals: list[RankingSignalItem] = Field(default_factory=list)


class BrandSummary(BaseModel):
    """Thông tin brand gắn với POI."""

    id: str
    name: str
    category: str | None = None
    subcategory: str | None = None


class PoiItem(BaseModel):
    """POI trả về sau khi lọc."""

    id: str
    name: str
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
    brand: BrandSummary | None = None


class PoiFilterResponse(BaseModel):
    """Kết quả lọc POI."""

    count: int
    items: list[PoiItem]
