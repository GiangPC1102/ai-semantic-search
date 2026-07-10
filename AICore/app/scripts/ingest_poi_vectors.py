"""Ingest POI descriptions from PostgreSQL into Qdrant collection ``poi_data``."""

from __future__ import annotations

import asyncio
import sys
import uuid

from prisma import Prisma

from app.core.config import settings
from app.core.logger import logger
from app.services.vector_store import VectorStore, VectorStoreError

POI_COLLECTION_NAME = settings.QDRANT_POI_COLLECTION
UPSERT_BATCH_SIZE = settings.VECTOR_UPSERT_BATCH_SIZE


def _resolve_point_id(existing_vector_id: str | None) -> str:
    """Reuse stored vector UUID when valid; otherwise generate a new one."""
    if existing_vector_id:
        try:
            return str(uuid.UUID(existing_vector_id))
        except ValueError:
            pass
    return str(uuid.uuid4())


async def _fetch_pois_with_description(db: Prisma) -> list:
    """Load POI rows that have a non-empty description."""
    pois = await db.poi.find_many(
        where={"description": {"not": None}},
        order={"id": "asc"},
    )
    return [
        poi
        for poi in pois
        if poi.description is not None and poi.description.strip()
    ]


async def ingest_poi_vectors(
    collection_name: str = POI_COLLECTION_NAME,
    batch_size: int = UPSERT_BATCH_SIZE,
    recreate: bool = False,
) -> int:
    """Embed POI descriptions and upsert into Qdrant.

    Args:
        collection_name: Target Qdrant collection (default ``poi_data``).
        batch_size: Embed/upsert batch size.
        recreate: Drop and recreate the collection before ingest.

    Returns:
        Number of POI vectors upserted.
    """
    db = Prisma()
    store = VectorStore()

    await db.connect()
    try:
        pois = await _fetch_pois_with_description(db)
        if not pois:
            logger.warning("No POI with description found — nothing to ingest")
            return 0

        if recreate and store.collection_exists(collection_name):
            store.qdrant_client.delete_collection(collection_name)
            logger.info("Deleted existing collection: %s", collection_name)

        store.ensure_poi_collection(
            collection_name,
            embedding_size=settings.EMBEDDING_SIZE,
        )

        texts = [poi.description.strip() for poi in pois]
        metadatas = [
            {"poi_id": poi.id, "name": poi.name}
            for poi in pois
        ]
        # Qdrant point IDs must be UUID/int — POI business ids (e.g. A001) are not
        point_ids = [_resolve_point_id(poi.vectorId) for poi in pois]

        logger.info(
            "Ingesting %s POI descriptions into %s (batch_size=%s)",
            len(texts),
            collection_name,
            batch_size,
        )

        upserted_ids = store.upsert(
            collection_name=collection_name,
            data={
                "text": texts,
                "metadata": metadatas,
                "ids": point_ids,
            },
            batch_size=batch_size,
            flow="poi",
        )

        for poi, vector_id in zip(pois, upserted_ids, strict=True):
            await db.poi.update(
                where={"id": poi.id},
                data={"vectorId": vector_id},
            )

        logger.info(
            "Ingest complete: %s vectors in collection %s",
            len(upserted_ids),
            collection_name,
        )
        return len(upserted_ids)
    except VectorStoreError:
        raise
    finally:
        await db.disconnect()
        store.embedding_client.close()


def main() -> None:
    """CLI entry point."""
    recreate = "--recreate" in sys.argv
    count = asyncio.run(ingest_poi_vectors(recreate=recreate))
    print(f"Upserted {count} POI vectors into '{POI_COLLECTION_NAME}'")


if __name__ == "__main__":
    main()
