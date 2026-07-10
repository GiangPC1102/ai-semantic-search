from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.signal_ranking import QueryUnderstandOutput


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Câu truy vấn tìm kiếm địa điểm")
    top_k: int = Field(default=10, ge=1, le=50)


class POIResult(BaseModel):
    poi_id: str | int
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[POIResult]
    query_analysis: QueryUnderstandOutput
    total: int
