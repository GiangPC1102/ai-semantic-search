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
    2. Hard-filter POIs
    3. Collect vectorIds
    4. Parallel POI + attribute vector search
    5. Keep POI hits that have attributes from attribute search

    Example body:

    ```json
    {
      "query": "quán cafe yên tĩnh có wifi ở Quận 1",
      "poi_top_k": 20,
      "attribute_top_k": 20
    }
    ```
    """
    service = TascoSearchService()
    try:
        return await service.search(
            query=body.query,
            poi_top_k=body.poi_top_k,
            attribute_top_k=body.attribute_top_k,
        )
    except (TascoSearchError, QueryUnderstandError) as exc:
        message = str(exc)
        if "rỗng" in message.lower() or "empty" in message.lower():
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=502, detail=message) from exc
    finally:
        service.close()
