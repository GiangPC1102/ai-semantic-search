"""Schemas for unified vector search API (POI / attribute)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SearchFlow = Literal["poi", "attribute"]


class VectorSearchRequest(BaseModel):
    """Request body for hybrid vector search."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language search query",
        examples=["quán cafe yên tĩnh view đẹp"],
    )
    flow: SearchFlow = Field(
        ...,
        description='Search flow: "poi" (dense+sparse+ColBERT) or "attribute" (dense+sparse+RRF)',
        examples=["poi"],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return",
    )
    prefetch_limit: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Prefetch candidates per branch; defaults depend on flow/config",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        description="RRF score cutoff for attribute flow; ignored for poi",
    )
    collection_name: str | None = Field(
        default=None,
        description="Override Qdrant collection; defaults to flow-specific config",
    )


class VectorSearchHit(BaseModel):
    """One vector search hit."""

    id: str
    score: float | None = None
    poi_id: str | None = None
    attribute_id: str | None = None
    name: str | None = None
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class VectorSearchResponse(BaseModel):
    """Unified hybrid search response."""

    query: str
    flow: SearchFlow
    collection: str
    count: int
    score_threshold: float | None = None
    items: list[VectorSearchHit]
