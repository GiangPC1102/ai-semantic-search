from __future__ import annotations

from typing import List

from fastapi import APIRouter, Body, HTTPException

from app.core.config import settings
from app.grpc.embedding.embedding_client import EmbeddingServiceClient
from app.schemas.embedding import EmbedHybridResponse

router = APIRouter()


@router.post("/hybrid", response_model=List[EmbedHybridResponse])
def embed_hybrid_documents(texts: List[str] = Body(..., embed=True)) -> List[EmbedHybridResponse]:
    """Embed a list of documents into hybrid vectors."""
    client = EmbeddingServiceClient(
        settings.EMBEDDING_SERVICE_URL, settings.EMBEDDING_SERVICE_TIMEOUT
    )
    try:
        result = client.embed_hybrid_documents(texts, settings.EMBEDDING_SERVICE_MODEL)
        return [EmbedHybridResponse(**item) for item in result]
        return [EmbedHybridResponse(**item) for item in result]
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Embedding service error: {e}"
        )
    finally:
        client.close()
