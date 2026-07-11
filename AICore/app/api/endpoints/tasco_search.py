"""API endpoint for end-to-end Tasco search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.helpers.query_understand import QueryUnderstandError
from app.schemas.tasco_search import TascoSearchRequest, TascoSearchResponse
from app.services.tasco_search import TascoSearchError, TascoSearchService

router = APIRouter()


@router.post("/search", response_model=TascoSearchResponse)
async def tasco_search(body: TascoSearchRequest) -> TascoSearchResponse:
    """Tasco search pipeline.

    Flow:
    1. Query understanding → normalized_query + hard_filters + signals
    2. Hard-filter POIs (cache full Poi rows + brand)
    3. Collect vectorIds
    4. POI hybrid search (+ attribute search only if ``is_filter_attribute``)
    5. Optional attribute intersect; attach ``poi`` detail from step-2 cache

    Example body:

    ```json
    {
      "query": "quán cafe yên tĩnh có wifi ở Quận 1",
      "poi_top_k": 20,
      "attribute_top_k": 20,
      "is_filter_attribute": false
    }
    ```
    """
    service = TascoSearchService()
    try:
        return await service.search(
            query=body.query,
            poi_top_k=body.poi_top_k,
            attribute_top_k=body.attribute_top_k,
            is_filter_attribute=body.is_filter_attribute,
        )
    except (TascoSearchError, QueryUnderstandError) as exc:
        message = str(exc)
        if "rỗng" in message.lower() or "empty" in message.lower():
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=502, detail=message) from exc
    finally:
        service.close()
