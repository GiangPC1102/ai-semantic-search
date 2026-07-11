from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.helpers.query_understand import QueryUnderstandError, QueryUnderstander
from app.schemas.search import POIResult, SearchRequest, SearchResponse
from app.services.vector_store import VectorStore

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_poi(body: SearchRequest) -> SearchResponse:
    """Tìm kiếm POI bằng hybrid search — query understanding + vector search."""
    understander = QueryUnderstander()
    try:
        analysis = await understander.aunderstand(body.query)
    except QueryUnderstandError as exc:
        message = str(exc)
        status = 400 if "rỗng" in message.lower() else 502
        raise HTTPException(status_code=status, detail=message) from exc

    search_query = analysis.normalized_query or body.query
    vector_store = VectorStore()
    try:
        raw = await asyncio.to_thread(
            vector_store.poi_search,
            settings.SEARCH_COLLECTION_NAME,
            search_query,
            body.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search error: {exc}") from exc

    results = [
        POIResult(
            poi_id=p.payload.get("poi_id", p.id) if p.payload else p.id,
            text=p.payload.get("text", "") if p.payload else "",
            score=p.score,
        )
        for p in raw.points
    ]
    return SearchResponse(results=results, query_analysis=analysis, total=len(results))
