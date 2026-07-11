"""Unified API endpoint for POI / attribute vector search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.vector_search import (
    VectorSearchHit,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.vector_store import VectorStore, VectorStoreError

router = APIRouter()

_DEFAULT_POI_PREFETCH_LIMIT = 100


@router.post("/search", response_model=VectorSearchResponse)
def search_vectors(body: VectorSearchRequest) -> VectorSearchResponse:
    """Hybrid vector search for POI or attribute collections.

    Example body (POI):

    ```json
    {
      "query": "quán cafe yên tĩnh view đẹp",
      "flow": "poi",
      "top_k": 5
    }
    ```

    Example body (attribute):

    ```json
    {
      "query": "có wifi và chỗ đậu xe",
      "flow": "attribute",
      "top_k": 5,
      "score_threshold": 0.01
    }
    ```
    """
    if body.flow == "poi":
        collection_name = body.collection_name or settings.QDRANT_POI_COLLECTION
        prefetch_limit = body.prefetch_limit or _DEFAULT_POI_PREFETCH_LIMIT
        score_threshold: float | None = None
    else:
        collection_name = body.collection_name or settings.QDRANT_ATTRIBUTE_COLLECTION
        prefetch_limit = body.prefetch_limit
        score_threshold = (
            body.score_threshold
            if body.score_threshold is not None
            else settings.ATTRIBUTE_SEARCH_RRF_THRESHOLD
        )

    store = VectorStore()
    try:
        hits = store.search(
            collection_name=collection_name,
            query=body.query,
            top_k=body.top_k,
            flow=body.flow,
            prefetch_limit=prefetch_limit,
            score_threshold=score_threshold,
        )
    except VectorStoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        store.embedding_client.close()

    items = [VectorSearchHit(**hit) for hit in hits]
    return VectorSearchResponse(
        query=body.query,
        flow=body.flow,
        collection=collection_name,
        count=len(items),
        score_threshold=score_threshold,
        items=items,
    )
