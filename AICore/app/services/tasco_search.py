"""Tasco search orchestration — understand → hard-filter → vector search → intersect."""

from __future__ import annotations

import asyncio
from typing import Any

from prisma.models import Attribute, Poi

from app.core.config import settings
from app.core.database import get_store
from app.core.logger import logger
from app.helpers.poi_signal_reranker import rerank_poi_hits_by_signals
from app.helpers.query_understand import QueryUnderstandError, QueryUnderstander
from app.schemas.signal_ranking import (
    HardFilters,
    QueryLanguage,
    QueryUnderstandOutput,
    RankingSignalItem,
)
from app.schemas.tasco_search import (
    PoiDetail,
    SearchExplain,
    TascoSearchItem,
    TascoSearchResponse,
)
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
        """Run the full Tasco search pipeline."""
        resolved_poi_top_k = poi_top_k or settings.TASCO_POI_TOP_K
        resolved_attr_top_k = attribute_top_k or settings.TASCO_ATTRIBUTE_TOP_K

        pre_embed_task = asyncio.create_task(
            asyncio.to_thread(self._vector_store.embed_query, query)
        )

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

        try:
            hard_filter_result, query_emb = await asyncio.gather(
                self._store.filter_hard_hint(
                    understood.hard_filters,
                    understood.ranking_signals,
                ),
                pre_embed_task,
            )
        except (StoreError, VectorStoreError) as exc:
            raise TascoSearchError(str(exc)) from exc

        filtered_pois = hard_filter_result.pois
        subcategory_applied = hard_filter_result.subcategory_applied
        vector_ids = [poi.vectorId for poi in filtered_pois if poi.vectorId]
        poi_by_id = {poi.id: poi for poi in filtered_pois}

        if not vector_ids:
            logger.info(
                "Tasco search: no vectorIds after hard filter (pois=%s)",
                len(filtered_pois),
            )
            return self._empty_response(
                understood,
                search_query,
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

        matched_attribute_ids = {
            hit["attribute_id"]
            for hit in attribute_hits
            if hit.get("attribute_id")
        }

        if is_filter_attribute and not matched_attribute_ids:
            items: list[TascoSearchItem] = []
        else:
            items = self._items_from_poi_hits(poi_hits, poi_by_id)

        poi_ids = [item.poi_id for item in items if item.poi_id]
        try:
            poi_attr_map = await self._store.get_attribute_ids_by_poi_ids(poi_ids)
        except StoreError as exc:
            raise TascoSearchError(str(exc)) from exc

        if is_filter_attribute and matched_attribute_ids:
            filtered_items: list[TascoSearchItem] = []
            for item in items:
                if not item.poi_id:
                    continue
                overlap = sorted(
                    poi_attr_map.get(item.poi_id, set()) & matched_attribute_ids
                )
                if not overlap:
                    continue
                filtered_items.append(
                    item.model_copy(
                        update={
                            "matched_attribute_ids": overlap,
                            "matched_attribute_count": len(overlap),
                        }
                    )
                )
            items = filtered_items
            items.sort(key=lambda i: i.matched_attribute_count, reverse=True)

        attr_ids: set[str] = set(matched_attribute_ids)
        for poi_id in (item.poi_id for item in items if item.poi_id):
            attr_ids |= poi_attr_map.get(poi_id, set())

        attr_map: dict[str, Attribute] = {}
        if attr_ids:
            try:
                attr_map = await self._store.get_attributes_by_ids(attr_ids)
            except StoreError as exc:
                raise TascoSearchError(str(exc)) from exc

        language = understood.language
        items = self._enrich_items(
            items,
            poi_attr_map=poi_attr_map,
            attr_map=attr_map,
            hard_filters=understood.hard_filters,
            subcategory_applied=subcategory_applied,
            ranking_signals=understood.ranking_signals,
            language=language,
        )

        return TascoSearchResponse(
            original_query=understood.original_query,
            normalized_query=search_query,
            hard_filtered_poi_count=len(filtered_pois),
            poi_hits_count=len(poi_hits),
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
        """Attach ``signal_name_vi`` from DB map."""
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
        """Map POI vector hits to response items."""
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
                    payload=dict(hit.get("payload") or {}),
                    poi=TascoSearchService._poi_to_detail(poi) if poi else None,
                )
            )
        return items

    @staticmethod
    def _enrich_items(
        items: list[TascoSearchItem],
        poi_attr_map: dict[str, set[str]],
        attr_map: dict[str, Attribute],
        hard_filters: HardFilters,
        subcategory_applied: bool,
        ranking_signals: list[RankingSignalItem],
        language: QueryLanguage,
    ) -> list[TascoSearchItem]:
        """Fill ``attributes`` + ``explain`` on each item."""
        signal_labels = [
            s.signal.value
            if language == QueryLanguage.EN
            else (s.signal_name_vi or s.signal.value)
            for s in ranking_signals
        ]

        result: list[TascoSearchItem] = []
        for item in items:
            poi_attr_ids = (
                sorted(poi_attr_map.get(item.poi_id, set())) if item.poi_id else []
            )
            all_labels = [
                label
                for attr_id in poi_attr_ids
                if (label := TascoSearchService._attr_label(
                    attr_map.get(attr_id), language
                ))
            ]
            matched_labels = [
                label
                for attr_id in item.matched_attribute_ids
                if (label := TascoSearchService._attr_label(
                    attr_map.get(attr_id), language
                ))
            ]
            hard_attrs: dict[str, str] = {}
            poi = item.poi
            if poi is not None:
                if hard_filters.brand and poi.brand_name:
                    hard_attrs["brand"] = poi.brand_name
                if hard_filters.category and poi.category:
                    hard_attrs["category"] = poi.category
                if (
                    subcategory_applied
                    and hard_filters.subcategory
                    and poi.subcategory
                ):
                    hard_attrs["subcategory"] = poi.subcategory
                if hard_filters.city and poi.city:
                    hard_attrs["city"] = poi.city
                if hard_filters.district and poi.district:
                    hard_attrs["district"] = poi.district

            result.append(
                item.model_copy(
                    update={
                        "attributes": all_labels,
                        "explain": SearchExplain(
                            hard_attributes=hard_attrs,
                            ranking_signals=list(signal_labels),
                            attributes=matched_labels,
                        ),
                    }
                )
            )
        return result

    @staticmethod
    def _attr_label(attr: Attribute | None, language: QueryLanguage) -> str | None:
        """EN → english_name; VI/mixed → attribute_name."""
        if attr is None:
            return None
        if language == QueryLanguage.EN:
            return attr.englishName or attr.attributeName
        return attr.attributeName

    @staticmethod
    def _poi_to_detail(poi: Poi) -> PoiDetail:
        """Map Prisma Poi (+ brand) to API detail."""
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
    def _empty_response(
        understood: QueryUnderstandOutput,
        search_query: str,
        hard_filtered_poi_count: int,
    ) -> TascoSearchResponse:
        """Build an empty pipeline response."""
        return TascoSearchResponse(
            original_query=understood.original_query,
            normalized_query=search_query,
            hard_filtered_poi_count=hard_filtered_poi_count,
            poi_hits_count=0,
            count=0,
            items=[],
        )
