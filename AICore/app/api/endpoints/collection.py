import asyncio
from app.core.config import settings
from fastapi import APIRouter, HTTPException
from app.services.vector_store import VectorStore
from app.schemas.collection import (
    CreateCollectionRequest,
    UpsertDocumentsRequest,
    UpsertPoiDocumentsRequest,
)


router = APIRouter()


@router.post("/create_collection")
async def create_collection(body: CreateCollectionRequest) -> dict:
    """Create a Qdrant collection."""

    vector_store = VectorStore()
    try:
        await asyncio.to_thread(
            vector_store.create_collection,
            body.collection_name,
            body.collection_type,
            settings.EMBEDDING_SIZE,
        )
        return {
            "success": True,
            "collection_name": body.collection_name,
            "collection_type": body.collection_type,
            "message": f"Collection '{body.collection_name}' created successfully.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create collection '{body.collection_name}': {e}",
        )


@router.post("/upsert_documents")
async def upsert_documents(body: UpsertDocumentsRequest) -> dict:
    """Upsert documents into a Qdrant collection."""

    vector_store = VectorStore()
    try:
        if isinstance(body, UpsertPoiDocumentsRequest):
            data = [
                {"id": str(id_), "text": text, "poi_id": poi_id}
                for id_, text, poi_id in zip(body.ids, body.texts, body.poi_ids)
            ]
        else:
            data = [
                {"id": str(id_), "text": text, "attribute_id": attribute_id}
                for id_, text, attribute_id in zip(
                    body.ids, body.texts, body.attribute_ids
                )
            ]
        await asyncio.to_thread(
            vector_store.upsert,
            body.collection_name,
            body.collection_type,
            data,
            body.batch_size,
        )
        return {
            "success": True,
            "collection_name": body.collection_name,
            "collection_type": body.collection_type,
            "message": f"Successfully upserted documents into '{body.collection_name}'.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upsert documents into '{body.collection_name}': {e}",
        )
