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
from app.schemas.signal_ranking import QueryLanguage, QueryUnderstandOutput
from app.schemas.tasco_search import PoiDetail, TascoSearchItem, TascoSearchResponse
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
        is_filter_attribute: bool = False,
    ) -> TascoSearchResponse:
        """Run the full Tasco search pipeline.

        Flow:
            1. Query understanding → normalized_query, hard_filters, signals
            2. Hard-filter POIs (+ opening_hours if present) — cache full Poi rows
            3. Collect vectorIds from filtered POIs
            4. POI hybrid search; attribute search only if ``is_filter_attribute``
            5. Rerank POI hits by price/rating/popularity/review signals (if any)
            6. If ``is_filter_attribute``: intersect attributes; else map POI hits directly
               Attach PoiDetail from step-2 cache (no extra DB query)
        """
        resolved_poi_top_k = poi_top_k or settings.TASCO_POI_TOP_K
        resolved_attr_top_k = attribute_top_k or settings.TASCO_ATTRIBUTE_TOP_K

        # Start embedding the raw query immediately — runs concurrently with the LLM
        # call below. Normalization rarely changes semantic content enough to affect
        # retrieval quality, so the raw-query embedding is reused for vector search.
        pre_embed_task = asyncio.create_task(
            asyncio.to_thread(self._vector_store.embed_query, query)
        )

        # LLM call and signal DB fetch are independent — run in parallel.
        try:
            understood, signal_vi_map = await asyncio.gather(
                asyncio.to_thread(self._understander.understand, query),
                self._store.get_signal_vietnam_names(),
            )
        except (QueryUnderstandError, StoreError) as exc:
            pre_embed_task.cancel()
            raise TascoSearchError(str(exc)) from exc
        except BaseException:
            pre_embed_task.cancel()
            raise
        understood = self._enrich_signals_with_vi_names(understood, signal_vi_map)

        search_query = understood.normalized_query or query

        # Hard-filter POIs and wait for the pre-started embedding concurrently —
        # both depend on LLM output but are independent of each other.
        try:
            filtered_pois, query_emb = await asyncio.gather(
                self._store.filter_hard_hint(
                    understood.hard_filters,
                    understood.ranking_signals,
                ),
                pre_embed_task,
            )
        except (StoreError, VectorStoreError) as exc:
            raise TascoSearchError(str(exc)) from exc

        vector_ids = [poi.vectorId for poi in filtered_pois if poi.vectorId]
        poi_by_id = {poi.id: poi for poi in filtered_pois}

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
            if is_filter_attribute:
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
                        query_emb,
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
                        query_emb,
                    ),
                )
            else:
                attribute_hits = []
                poi_hits = await asyncio.to_thread(
                    self._vector_store.search,
                    settings.QDRANT_POI_COLLECTION,
                    search_query,
                    resolved_poi_top_k,
                    "poi",
                    None,
                    None,
                    vector_ids,
                    query_emb,
                )
        except VectorStoreError as exc:
            raise TascoSearchError(str(exc)) from exc

        poi_hits = rerank_poi_hits_by_signals(
            poi_hits,
            poi_by_id,
            understood.ranking_signals,
        )

        if not is_filter_attribute:
            items = self._items_from_poi_hits(poi_hits, poi_by_id)
            return TascoSearchResponse(
                original_query=understood.original_query,
                normalized_query=search_query,
                hard_filters=understood.hard_filters,
                ranking_signals=understood.ranking_signals,
                hard_filtered_poi_count=len(filtered_pois),
                poi_hits_count=len(poi_hits),
                attribute_hits=[],
                count=len(items),
                items=items,
            )

        matched_attribute_ids = {
            hit["attribute_id"]
            for hit in attribute_hits
            if hit.get("attribute_id")
        }

        # Chỉ cần englishName khi display tiếng Anh; vi/mixed dùng luôn name Việt
        # đã lưu trong Qdrant → bỏ qua DB call cho majority case.
        attr_map: dict[str, Any] = {}
        if understood.language == QueryLanguage.EN and matched_attribute_ids:
            try:
                attr_map = await self._store.get_attributes_by_ids(
                    matched_attribute_ids,
                )
            except StoreError as exc:
                raise TascoSearchError(str(exc)) from exc

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
            attribute_hits=self._localize_attribute_hits(
                attribute_hits,
                attr_map,
                understood.language,
            ),
            count=len(items),
            items=items,
        )

    def close(self) -> None:
        """Close owned embedding client if created by this service."""
        if self._owns_vector_store:
            self._vector_store.embedding_client.close()

    @staticmethod
    def _enrich_signals_with_vi_names(
        understood: QueryUnderstandOutput,
        signal_vi_map: dict[str, str],
    ) -> QueryUnderstandOutput:
        """Attach ``signal_name_vi`` to each ranking signal from the DB map."""
        if not signal_vi_map or not understood.ranking_signals:
            return understood
        enriched = [
            item.model_copy(
                update={"signal_name_vi": signal_vi_map.get(item.signal.value)}
            )
            for item in understood.ranking_signals
        ]
        return understood.model_copy(update={"ranking_signals": enriched})

    @staticmethod
    def _items_from_poi_hits(
        poi_hits: list[dict[str, Any]],
        poi_by_id: dict[str, Poi],
    ) -> list[TascoSearchItem]:
        """Map POI vector hits to response items without attribute intersection."""
        items: list[TascoSearchItem] = []
        for hit in poi_hits:
            poi_id = hit.get("poi_id")
            if not poi_id:
                continue
            poi = poi_by_id.get(poi_id)
            items.append(
                TascoSearchItem(
                    poi_id=poi_id,
                    vector_id=str(hit.get("id", "")),
                    name=hit.get("name") or (poi.name if poi else None),
                    text=hit.get("text"),
                    score=hit.get("score"),
                    matched_attribute_count=0,
                    matched_attribute_ids=[],
                    payload=dict(hit.get("payload") or {}),
                    poi=TascoSearchService._poi_to_detail(poi) if poi else None,
                )
            )
        return items

    @staticmethod
    def _intersect_poi_with_attributes(
        poi_hits: list[dict[str, Any]],
        matched_attribute_ids: set[str],
        poi_attr_map: dict[str, set[str]],
        poi_by_id: dict[str, Poi],
    ) -> list[TascoSearchItem]:
        """Keep POI hits that share attributes with attribute search, then rerank.

        Ranking: more matched attributes first. Within the same count, preserve
        prior order (signal rerank / vector score) via Python stable sort.
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
                    poi=TascoSearchService._poi_to_detail(poi) if poi else None,
                )
            )

        items.sort(
            key=lambda item: item.matched_attribute_count,
            reverse=True,
        )
        return items

    @staticmethod
    def _poi_to_detail(poi: Poi) -> PoiDetail:
        """Map a Prisma Poi (already loaded at hard-filter) to API detail."""
        brand = poi.brand
        return PoiDetail(
            id=poi.id,
            name=poi.name,
            brand_id=poi.brandId,
            brand_name=brand.name if brand else None,
            category=brand.category if brand else None,
            subcategory=brand.subcategory if brand else None,
            city=poi.city,
            district=poi.district,
            address=poi.address,
            longitude=poi.longitude,
            latitude=poi.latitude,
            rating=poi.rating,
            review_count=poi.reviewCount,
            popularity_score=poi.popularityScore,
            price_level=poi.priceLevel,
            open_hours=poi.openHours,
            description=poi.description,
            vector_id=poi.vectorId,
        )

    @staticmethod
    def _localize_attribute_hits(
        hits: list[dict[str, Any]],
        attr_map: dict[str, Any],
        language: QueryLanguage,
    ) -> list[VectorSearchHit]:
        """Build attribute hits with ``name`` in the query's language.

        English queries get the attribute's ``englishName`` (fallback to the
        stored Vietnamese name); Vietnamese / mixed queries keep the Vietnamese
        name — consistent with the normalized query used for search.
        """
        localized: list[VectorSearchHit] = []
        for hit in hits:
            if language == QueryLanguage.EN:
                attr = attr_map.get(hit.get("attribute_id"))
                if attr and attr.englishName:
                    hit = {**hit, "name": attr.englishName}
            localized.append(VectorSearchHit(**hit))
        return localized

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
