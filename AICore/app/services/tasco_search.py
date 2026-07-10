"""Tasco search orchestration — understand → hard-filter → parallel vector search → intersect."""

from __future__ import annotations

import asyncio
from typing import Any

from prisma.models import Poi

from app.core.config import settings
from app.core.database import get_store
from app.core.logger import logger
from app.helpers.poi_signal_reranker import rerank_poi_hits_by_signals
from app.helpers.query_understand import QueryUnderstandError, QueryUnderstander
from app.schemas.tasco_search import TascoSearchItem, TascoSearchResponse
from app.schemas.vector_search import VectorSearchHit
from app.services.store import Store, StoreError
from app.services.vector_store import VectorStore, VectorStoreError


class TascoSearchError(Exception):
    """Raised when the Tasco search pipeline fails."""


class TascoSearchService:
    """Orchestrate query understanding, hard filter, and hybrid vector search."""

    def __init__(
        self,
        store: Store | None = None,
        vector_store: VectorStore | None = None,
        understander: QueryUnderstander | None = None,
    ) -> None:
        self._store = store or get_store()
        self._vector_store = vector_store or VectorStore()
        self._understander = understander or QueryUnderstander()
        self._owns_vector_store = vector_store is None

    async def search(
        self,
        query: str,
        poi_top_k: int | None = None,
        attribute_top_k: int | None = None,
    ) -> TascoSearchResponse:
        """Run the full Tasco search pipeline.

        Flow:
            1. Query understanding → normalized_query, hard_filters, signals
            2. Hard-filter POIs (+ opening_hours if present)
            3. Collect vectorIds from filtered POIs
            4. Parallel POI + attribute vector search
            5. Rerank POI hits by price/rating/popularity/review signals (if any)
            6. Keep POI hits that share attributes with attribute hits
        """
        resolved_poi_top_k = poi_top_k or settings.TASCO_POI_TOP_K
        resolved_attr_top_k = attribute_top_k or settings.TASCO_ATTRIBUTE_TOP_K

        try:
            understood = await asyncio.to_thread(
                self._understander.understand,
                query,
            )
        except QueryUnderstandError as exc:
            raise TascoSearchError(str(exc)) from exc

        try:
            filtered_pois = await self._store.filter_hard_hint(
                understood.hard_filters,
                understood.ranking_signals,
            )
        except StoreError as exc:
            raise TascoSearchError(str(exc)) from exc

        vector_ids = [poi.vectorId for poi in filtered_pois if poi.vectorId]
        poi_by_id = {poi.id: poi for poi in filtered_pois}
        search_query = understood.normalized_query or query

        if not vector_ids:
            logger.info(
                "Tasco search: no vectorIds after hard filter (pois=%s)",
                len(filtered_pois),
            )
            return self._empty_response(
                understood.original_query,
                search_query,
                understood.hard_filters,
                understood.ranking_signals,
                hard_filtered_poi_count=len(filtered_pois),
            )

        try:
            poi_hits, attribute_hits = await asyncio.gather(
                asyncio.to_thread(
                    self._vector_store.search,
                    settings.QDRANT_POI_COLLECTION,
                    search_query,
                    resolved_poi_top_k,
                    "poi",
                    None,
                    None,
                    vector_ids,
                ),
                asyncio.to_thread(
                    self._vector_store.search,
                    settings.QDRANT_ATTRIBUTE_COLLECTION,
                    search_query,
                    resolved_attr_top_k,
                    "attribute",
                    None,
                    None,
                    None,
                ),
            )
        except VectorStoreError as exc:
            raise TascoSearchError(str(exc)) from exc

        poi_hits = rerank_poi_hits_by_signals(
            poi_hits,
            poi_by_id,
            understood.ranking_signals,
        )

        matched_attribute_ids = {
            hit["attribute_id"]
            for hit in attribute_hits
            if hit.get("attribute_id")
        }

        poi_ids_from_hits = [
            hit["poi_id"] for hit in poi_hits if hit.get("poi_id")
        ]
        try:
            poi_attr_map = await self._store.get_attribute_ids_by_poi_ids(
                poi_ids_from_hits,
            )
        except StoreError as exc:
            raise TascoSearchError(str(exc)) from exc

        items = self._intersect_poi_with_attributes(
            poi_hits=poi_hits,
            matched_attribute_ids=matched_attribute_ids,
            poi_attr_map=poi_attr_map,
            poi_by_id=poi_by_id,
        )

        return TascoSearchResponse(
            original_query=understood.original_query,
            normalized_query=search_query,
            hard_filters=understood.hard_filters,
            ranking_signals=understood.ranking_signals,
            hard_filtered_poi_count=len(filtered_pois),
            poi_hits_count=len(poi_hits),
            attribute_hits=[VectorSearchHit(**hit) for hit in attribute_hits],
            count=len(items),
            items=items,
        )

    def close(self) -> None:
        """Close owned embedding client if created by this service."""
        if self._owns_vector_store:
            self._vector_store.embedding_client.close()

    @staticmethod
    def _intersect_poi_with_attributes(
        poi_hits: list[dict[str, Any]],
        matched_attribute_ids: set[str],
        poi_attr_map: dict[str, set[str]],
        poi_by_id: dict[str, Poi],
    ) -> list[TascoSearchItem]:
        """Keep POI hits that share attributes with attribute search, then rerank.

        Ranking: more matched attributes first, then higher POI vector score.
        """
        if not matched_attribute_ids:
            return []

        items: list[TascoSearchItem] = []
        for hit in poi_hits:
            poi_id = hit.get("poi_id")
            if not poi_id:
                continue

            poi_attrs = poi_attr_map.get(poi_id, set())
            overlap = sorted(poi_attrs & matched_attribute_ids)
            if not overlap:
                continue

            poi = poi_by_id.get(poi_id)
            items.append(
                TascoSearchItem(
                    poi_id=poi_id,
                    vector_id=str(hit.get("id", "")),
                    name=hit.get("name") or (poi.name if poi else None),
                    text=hit.get("text"),
                    score=hit.get("score"),
                    matched_attribute_count=len(overlap),
                    matched_attribute_ids=overlap,
                    payload=dict(hit.get("payload") or {}),
                )
            )

        items.sort(
            key=lambda item: (
                item.matched_attribute_count,
                item.score if item.score is not None else float("-inf"),
            ),
            reverse=True,
        )
        return items

    @staticmethod
    def _empty_response(
        original_query: str,
        normalized_query: str,
        hard_filters: Any,
        ranking_signals: Any,
        hard_filtered_poi_count: int,
    ) -> TascoSearchResponse:
        """Build an empty pipeline response."""
        return TascoSearchResponse(
            original_query=original_query,
            normalized_query=normalized_query,
            hard_filters=hard_filters,
            ranking_signals=ranking_signals,
            hard_filtered_poi_count=hard_filtered_poi_count,
            poi_hits_count=0,
            attribute_hits=[],
            count=0,
            items=[],
        )
