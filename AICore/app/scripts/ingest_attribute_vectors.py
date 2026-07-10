"""Ingest attribute descriptions from PostgreSQL into Qdrant ``attribute_data``."""

from __future__ import annotations

import asyncio
import sys
import uuid

from prisma import Prisma

from app.core.config import settings
from app.core.logger import logger
from app.services.vector_store import VectorStore, VectorStoreError

ATTRIBUTE_COLLECTION_NAME = settings.QDRANT_ATTRIBUTE_COLLECTION
UPSERT_BATCH_SIZE = settings.VECTOR_UPSERT_BATCH_SIZE


def _resolve_point_id(existing_vector_id: str | None) -> str:
    """Reuse stored vector UUID when valid; otherwise generate a new one."""
    if existing_vector_id:
        try:
            return str(uuid.UUID(existing_vector_id))
        except ValueError:
            pass
    return str(uuid.uuid4())


async def _fetch_attributes_with_description(db: Prisma) -> list:
    """Load attribute rows that have a non-empty description."""
    attributes = await db.attribute.find_many(
        where={"description": {"not": None}},
        order={"id": "asc"},
    )
    return [
        attr
        for attr in attributes
        if attr.description is not None and attr.description.strip()
    ]


async def ingest_attribute_vectors(
    collection_name: str = ATTRIBUTE_COLLECTION_NAME,
    batch_size: int = UPSERT_BATCH_SIZE,
    recreate: bool = False,
) -> int:
    """Embed attribute descriptions and upsert into Qdrant.

    Args:
        collection_name: Target Qdrant collection (default ``attribute_data``).
        batch_size: Embed/upsert batch size.
        recreate: Drop and recreate the collection before ingest.

    Returns:
        Number of attribute vectors upserted.
    """
    db = Prisma()
    store = VectorStore()

    await db.connect()
    try:
        attributes = await _fetch_attributes_with_description(db)
        if not attributes:
            logger.warning("No attribute with description found — nothing to ingest")
            return 0

        if recreate and store.collection_exists(collection_name):
            store.qdrant_client.delete_collection(collection_name)
            logger.info("Deleted existing collection: %s", collection_name)

        store.ensure_attribute_collection(
            collection_name,
            embedding_size=settings.EMBEDDING_SIZE,
        )

        texts = [attr.description.strip() for attr in attributes]
        metadatas = [
            {
                "attribute_id": attr.id,
                "name": attr.attributeName,
            }
            for attr in attributes
        ]
        point_ids = [_resolve_point_id(attr.vectorId) for attr in attributes]

        logger.info(
            "Ingesting %s attribute descriptions into %s (batch_size=%s)",
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
            flow="attribute",
        )

        for attr, vector_id in zip(attributes, upserted_ids, strict=True):
            await db.attribute.update(
                where={"id": attr.id},
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
    count = asyncio.run(ingest_attribute_vectors(recreate=recreate))
    print(f"Upserted {count} attribute vectors into '{ATTRIBUTE_COLLECTION_NAME}'")


if __name__ == "__main__":
    main()
