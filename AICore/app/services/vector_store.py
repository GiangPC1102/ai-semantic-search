"""Qdrant vector store — create collections and upsert hybrid embeddings."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.core.logger import logger
from app.grpc.embedding.embedding_client import EmbeddingServiceClient

UpsertFlow = Literal["poi", "attribute"]


class VectorStoreError(Exception):
    """Raised when a vector-store operation fails."""


class VectorStore:
    """Client for Qdrant hybrid (dense + sparse + ColBERT) collections."""

    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        embedding_client: EmbeddingServiceClient | None = None,
    ) -> None:
        self.qdrant_client = qdrant_client or QdrantClient(
            host=settings.QDRANT_HOST,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=True,
        )
        self.embedding_client = embedding_client or EmbeddingServiceClient(
            service_url=settings.EMBEDDING_SERVICE_URL,
            timeout=settings.EMBEDDING_SERVICE_TIMEOUT,
        )

    def collection_exists(self, collection_name: str) -> bool:
        """Return whether ``collection_name`` already exists."""
        return self.qdrant_client.collection_exists(collection_name)

    def ensure_poi_collection(
        self,
        collection_name: str,
        embedding_size: int | None = None,
    ) -> None:
        """Create the POI hybrid collection if it does not exist."""
        if self.collection_exists(collection_name):
            logger.info("Collection already exists: %s", collection_name)
            return

        size = embedding_size or settings.EMBEDDING_SIZE
        self.create_poi_collection(collection_name, size)
        logger.info("Created POI collection: %s (dim=%s)", collection_name, size)

    def create_poi_collection(self, collection_name: str, embedding_size: int) -> None:
        """Create a hybrid POI collection (dense + ColBERT + sparse)."""
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                    hnsw_config=models.HnswConfigDiff(
                        m=settings.QDRANT_HNSW_M,
                        ef_construct=settings.QDRANT_HNSW_EF_CONSTRUCT,
                        full_scan_threshold=settings.QDRANT_HNSW_FULL_SCAN_THRESHOLD,
                        on_disk=True,
                        inline_storage=True,
                    ),
                    quantization_config=models.TurboQuantization(
                        turbo=models.TurboQuantQuantizationConfig(
                            bits=models.TurboQuantBitSize.BITS1_5,
                            always_ram=True,
                        )
                    ),
                ),
                "colbert": models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM,
                    ),
                    hnsw_config=models.HnswConfigDiff(m=0),
                    on_disk=True,
                    datatype=models.Datatype.FLOAT16,
                ),
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    )
                ),
            },
            on_disk_payload=True,
            optimizers_config=models.OptimizersConfigDiff(
                default_segment_number=settings.QDRANT_DEFAULT_SEGMENT_NUMBER,
                max_segment_size=settings.QDRANT_MAX_SEGMENT_SIZE,
                indexing_threshold=settings.QDRANT_INDEXING_THRESHOLD,
            ),
        )

    def ensure_attribute_collection(
        self,
        collection_name: str,
        embedding_size: int | None = None,
    ) -> None:
        """Create the attribute collection if it does not exist."""
        if self.collection_exists(collection_name):
            logger.info("Collection already exists: %s", collection_name)
            return

        size = embedding_size or settings.EMBEDDING_SIZE
        self.create_attribute_collection(collection_name, size)
        logger.info(
            "Created attribute collection: %s (dim=%s)",
            collection_name,
            size,
        )

    def create_attribute_collection(
        self,
        collection_name: str,
        embedding_size: int,
    ) -> None:
        """Create an attribute collection (dense + sparse)."""
        self.qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    )
                ),
            },
            on_disk_payload=True,
        )

    @staticmethod
    def _create_sparse_vector(sparse_weights: dict[str, float]) -> models.SparseVector:
        """Convert BGE-M3 lexical weights into a Qdrant sparse vector."""
        indices: list[int] = []
        values: list[float] = []
        for token_id, weight in sparse_weights.items():
            indices.append(int(token_id))
            values.append(float(weight))
        return models.SparseVector(indices=indices, values=values)

    def upsert(
        self,
        collection_name: str,
        data: dict[str, list[Any]],
        batch_size: int = 10,
        flow: UpsertFlow = "poi",
    ) -> list[str]:
        """Embed texts and upsert vectors into Qdrant.

        Args:
            collection_name: Target Qdrant collection.
            data: Mapping with keys:
                - ``text``: list[str] — documents to embed
                - ``metadata``: list[dict] — payload fields
                - ``ids`` (optional): list[str] — point IDs; UUID generated if omitted
            batch_size: Number of documents per embed/upsert batch.
            flow: ``"poi"`` → dense + sparse + ColBERT;
                ``"attribute"`` → dense + sparse only.

        Returns:
            List of upserted point IDs (same order as input texts).
        """
        if flow not in ("poi", "attribute"):
            raise VectorStoreError(f"Unsupported upsert flow: {flow}")

        texts: list[str] = data["text"]
        metadatas: list[dict[str, Any]] = data["metadata"]
        if len(texts) != len(metadatas):
            raise VectorStoreError(
                f"text/metadata length mismatch: {len(texts)} vs {len(metadatas)}"
            )

        provided_ids = data.get("ids")
        if provided_ids is not None:
            if len(provided_ids) != len(texts):
                raise VectorStoreError(
                    f"ids/text length mismatch: {len(provided_ids)} vs {len(texts)}"
                )
            ids = [str(point_id) for point_id in provided_ids]
        else:
            ids = [str(uuid.uuid4()) for _ in texts]

        include_colbert = flow == "poi"
        model_name = settings.EMBEDDING_SERVICE_MODEL
        upserted_ids: list[str] = []

        for batch_idx in range(0, len(texts), batch_size):
            batch_texts = texts[batch_idx : batch_idx + batch_size]
            batch_metadatas = metadatas[batch_idx : batch_idx + batch_size]
            batch_ids = ids[batch_idx : batch_idx + batch_size]

            try:
                hybrid_embeddings = self.embedding_client.embed_hybrid_documents(
                    batch_texts,
                    model=model_name,
                )
            except Exception as exc:
                raise VectorStoreError(
                    f"Embedding failed for batch starting at {batch_idx}: {exc}"
                ) from exc

            if len(hybrid_embeddings) != len(batch_texts):
                raise VectorStoreError(
                    "Embedding count mismatch: "
                    f"{len(hybrid_embeddings)} vs {len(batch_texts)}"
                )

            dense_vectors: list[list[float]] = []
            colbert_vectors: list[list[list[float]]] = []
            sparse_vectors: list[models.SparseVector] = []
            payloads: list[dict[str, Any]] = []

            for text, metadata, hybrid_embedding in zip(
                batch_texts,
                batch_metadatas,
                hybrid_embeddings,
                strict=True,
            ):
                dense_vectors.append(hybrid_embedding["dense_vector"])
                sparse_vectors.append(
                    self._create_sparse_vector(hybrid_embedding["sparse_weights"])
                )
                if include_colbert:
                    colbert_vectors.append(hybrid_embedding["colbert_vectors"])
                payloads.append(
                    json.loads(
                        json.dumps(
                            {"text": text, **metadata},
                            default=str,
                        )
                    )
                )

            vectors: dict[str, Any] = {
                "dense": dense_vectors,
                "sparse": sparse_vectors,
            }
            if include_colbert:
                vectors["colbert"] = colbert_vectors

            try:
                self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=models.Batch(
                        ids=batch_ids,
                        vectors=vectors,
                        payloads=payloads,
                    ),
                )
            except Exception as upsert_error:
                raise VectorStoreError(
                    f"Error upserting data to collection {collection_name}: "
                    f"{upsert_error}"
                ) from upsert_error

            upserted_ids.extend(batch_ids)
            logger.info(
                "Upserted %s batch %s–%s / %s into %s",
                flow,
                batch_idx + 1,
                batch_idx + len(batch_texts),
                len(texts),
                collection_name,
            )

        return upserted_ids

    def embed_query(self, query: str) -> dict[str, Any]:
        """Embed a single query and return the hybrid embedding dict.

        Callers that need to search multiple collections with the same query
        should call this once and pass the result as ``query_embedding`` to
        each ``search()`` call — avoiding redundant BGE-M3 inference.
        """
        try:
            embeddings = self.embedding_client.embed_hybrid_documents(
                [query],
                model=settings.EMBEDDING_SERVICE_MODEL,
            )
            if not embeddings:
                raise VectorStoreError("Empty embedding response for query")
            return embeddings[0]
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Query embedding failed: {exc}") from exc

    def search(
        self,
        collection_name: str,
        query: str,
        top_k: int,
        flow: UpsertFlow = "poi",
        prefetch_limit: int | None = None,
        score_threshold: float | None = None,
        point_ids: list[str] | None = None,
        query_embedding: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid vector search for POI or attribute collections.

        Args:
            collection_name: Target Qdrant collection.
            query: Natural-language query.
            top_k: Max results to return.
            flow: ``"poi"`` → dense + sparse prefetch, ColBERT rerank;
                ``"attribute"`` → dense + sparse → RRF → threshold → top_k.
            prefetch_limit: Candidates per dense/sparse branch.
            score_threshold: Minimum RRF score for attribute flow (config default).
            point_ids: Optional Qdrant point IDs to restrict search (e.g. POI vectorIds).

        Returns:
            Ranked hit dicts with id, score, name, text, payload, and
            ``poi_id`` or ``attribute_id`` depending on flow.
        """
        if top_k < 1:
            raise VectorStoreError("top_k must be >= 1")

        if point_ids is not None and len(point_ids) == 0:
            return []

        query_filter = None
        if point_ids:
            query_filter = models.Filter(
                must=[models.HasIdCondition(has_id=list(point_ids))],
            )

        if flow == "poi":
            resolved_prefetch = (
                prefetch_limit if prefetch_limit is not None else 100
            )
        else:
            resolved_prefetch = (
                prefetch_limit
                if prefetch_limit is not None
                else settings.ATTRIBUTE_SEARCH_PREFETCH_LIMIT
            )
            score_threshold = (
                score_threshold
                if score_threshold is not None
                else settings.ATTRIBUTE_SEARCH_RRF_THRESHOLD
            )

        try:
            if query_embedding is None:
                embeddings = self.embedding_client.embed_hybrid_documents(
                    [query],
                    model=settings.EMBEDDING_SERVICE_MODEL,
                )
                if not embeddings:
                    raise VectorStoreError("Empty embedding response for query")
                query_embedding = embeddings[0]

            dense_vector = query_embedding["dense_vector"]
            qdrant_sparse = self._create_sparse_vector(
                query_embedding["sparse_weights"],
            )

            start_time = time.time()

            if flow == "poi":
                results = self.qdrant_client.query_points(
                    collection_name=collection_name,
                    query_filter=query_filter,
                    prefetch=[
                        models.Prefetch(
                            query=qdrant_sparse,
                            using="sparse",
                            limit=resolved_prefetch,
                        ),
                        models.Prefetch(
                            query=dense_vector,
                            using="dense",
                            limit=resolved_prefetch,
                            params=models.SearchParams(
                                quantization=models.QuantizationSearchParams(
                                    rescore=True,
                                    oversampling=3.0,
                                )
                            ),
                        ),
                    ],
                    query=query_embedding["colbert_vectors"],
                    using="colbert",
                    with_payload=True,
                    limit=top_k,
                )
                logger.info("POI hybrid search took %.3fs", time.time() - start_time)
                return self._points_to_hits(results.points or [], flow="poi")

            fusion_limit = max(resolved_prefetch, top_k)
            results = self.qdrant_client.query_points(
                collection_name=collection_name,
                query_filter=query_filter,
                prefetch=[
                    models.Prefetch(
                        query=qdrant_sparse,
                        using="sparse",
                        limit=resolved_prefetch,
                    ),
                    models.Prefetch(
                        query=dense_vector,
                        using="dense",
                        limit=resolved_prefetch,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                with_payload=True,
                limit=fusion_limit,
            )
            logger.info(
                "Attribute hybrid+RRF search took %.3fs",
                time.time() - start_time,
            )

            hits = self._points_to_hits(
                results.points or [],
                flow="attribute",
                score_threshold=score_threshold,
            )
            return hits[:top_k]
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Error performing {flow} search: {exc}") from exc

    @staticmethod
    def _points_to_hits(
        points: list[Any],
        flow: UpsertFlow,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Map Qdrant points to normalized hit dicts."""
        hits: list[dict[str, Any]] = []
        for point in points:
            score = float(point.score) if point.score is not None else 0.0
            if score_threshold is not None and score < score_threshold:
                continue

            payload = dict(point.payload or {})
            hit: dict[str, Any] = {
                "id": str(point.id),
                "score": score,
                "name": payload.get("name"),
                "text": payload.get("text"),
                "payload": payload,
            }
            if flow == "poi":
                hit["poi_id"] = payload.get("poi_id")
            else:
                hit["attribute_id"] = payload.get("attribute_id")
            hits.append(hit)
        return hits
