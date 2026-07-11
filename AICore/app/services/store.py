"""PostgreSQL store — hard-filter POI qua Prisma."""

from __future__ import annotations

from typing import Any

from prisma import Prisma
from prisma.errors import PrismaError
from prisma.models import Poi

from app.core.logger import logger
from app.helpers.opening_hours_matcher import matches_opening_hours_preference
from app.schemas.signal_ranking import (
    HardFilters,
    OpeningHoursPreference,
    RankingSignalItem,
    RankingSignalType,
)


class StoreError(Exception):
    """Lỗi khi truy vấn database qua Prisma."""


class Store:
    """Kết nối PostgreSQL và lọc POI theo hard-filter từ query understanding."""

    def __init__(self, db: Prisma | None = None) -> None:
        self._db = db if db is not None else Prisma()
        self._is_connected = False

    async def connect(self) -> None:
        """Mở kết nối Prisma nếu chưa kết nối."""
        if not self._is_connected:
            await self._db.connect()
            self._is_connected = True

    async def disconnect(self) -> None:
        """Đóng kết nối Prisma."""
        if self._is_connected:
            await self._db.disconnect()
            self._is_connected = False

    async def __aenter__(self) -> Store:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    async def filter_hard_hint(
        self,
        hard_filters: HardFilters,
        signals: list[RankingSignalItem],
    ) -> list[Poi]:
        """Lọc POI theo hard-filter và signal ``opening_hours``.

        Hard-filter áp dụng trên DB:
        - ``brand``, ``category``, ``subcategory`` (qua bảng ``brands``)
        - ``city``, ``district`` (trên bảng ``poi``)

        Category / subcategory cascade:
        1. Có ``category`` → filter theo category trước.
        2. Có thêm ``subcategory`` → filter tiếp trên subcategory.
        3. Nếu subcategory trả về 0 → rollback về kết quả category.

        Signal ``opening_hours`` được lọc sau query:
        - ``open_time``: POI phải đang mở tại thời điểm đó
        - ``close_time``: POI phải còn mở tại thời điểm đó
        - ``is_24h``: POI phải mở 24/7

        Args:
            hard_filters: Bộ lọc cứng từ ``QueryUnderstandOutput``.
            signals: Danh sách ranking signals (dùng signal ``opening_hours``).

        Returns:
            Danh sách POI thỏa mãn, kèm ``brand`` nếu có.
        """
        await self.connect()

        opening_hours_pref = self._extract_opening_hours_preference(signals)
        pois = await self._query_with_category_rollback(hard_filters)

        if opening_hours_pref is None:
            return pois

        return [
            poi
            for poi in pois
            if matches_opening_hours_preference(poi.openHours, opening_hours_pref)
        ]

    async def _query_with_category_rollback(
        self,
        hard_filters: HardFilters,
    ) -> list[Poi]:
        """Query POI; rollback subcategory → category khi subcategory rỗng."""
        has_category = bool(hard_filters.category)
        has_subcategory = bool(hard_filters.subcategory)

        if not (has_category and has_subcategory):
            return await self._find_pois(
                self._build_where_clause(hard_filters),
            )

        category_pois = await self._find_pois(
            self._build_where_clause(hard_filters, include_subcategory=False),
        )
        subcategory_pois = [
            poi
            for poi in category_pois
            if self._poi_matches_subcategory(poi, hard_filters.subcategory)
        ]

        if not subcategory_pois:
            logger.info(
                "Subcategory filter empty (%s); rollback to category (%s) → %s POIs",
                hard_filters.subcategory,
                hard_filters.category,
                len(category_pois),
            )
            return category_pois

        return subcategory_pois

    async def _find_pois(self, where_clause: dict[str, Any]) -> list[Poi]:
        """Execute POI find_many with brand include."""
        try:
            return await self._db.poi.find_many(
                where=where_clause or None,
                include={"brand": True},
            )
        except PrismaError as exc:
            logger.error("filter_hard_hint query failed: %s", exc)
            raise StoreError(f"Truy vấn POI thất bại: {exc}") from exc

    @staticmethod
    def _poi_matches_subcategory(poi: Poi, subcategory: str | None) -> bool:
        """Case-insensitive contains match on brand.subcategory."""
        if not subcategory or poi.brand is None or not poi.brand.subcategory:
            return False
        return subcategory.strip().lower() in poi.brand.subcategory.lower()

    async def get_attribute_ids_by_poi_ids(
        self,
        poi_ids: list[str],
    ) -> dict[str, set[str]]:
        """Map each POI id to its linked attribute ids.

        Args:
            poi_ids: POI primary keys.

        Returns:
            ``{poi_id: {attribute_id, ...}}`` for POIs that have attributes.
        """
        if not poi_ids:
            return {}

        await self.connect()
        try:
            links = await self._db.poiattribute.find_many(
                where={"poiId": {"in": poi_ids}},
            )
        except PrismaError as exc:
            logger.error("get_attribute_ids_by_poi_ids failed: %s", exc)
            raise StoreError(f"Truy vấn poi_attributes thất bại: {exc}") from exc

        mapping: dict[str, set[str]] = {}
        for link in links:
            mapping.setdefault(link.poiId, set()).add(link.attributeId)
        return mapping

    @staticmethod
    def _build_where_clause(
        hard_filters: HardFilters,
        *,
        include_subcategory: bool = True,
    ) -> dict[str, Any]:
        """Xây dựng Prisma ``where`` từ hard-filter."""
        where: dict[str, Any] = {}

        if hard_filters.city:
            where["city"] = Store._insensitive_contains(hard_filters.city)

        if hard_filters.district:
            where["district"] = Store._insensitive_contains(hard_filters.district)

        brand_filter = Store._build_brand_filter(
            hard_filters,
            include_subcategory=include_subcategory,
        )
        if brand_filter:
            where["brand"] = {"is": brand_filter}

        return where

    @staticmethod
    def _build_brand_filter(
        hard_filters: HardFilters,
        *,
        include_subcategory: bool = True,
    ) -> dict[str, Any]:
        """Gom filter brand/category/subcategory trên relation ``brand``."""
        brand_filter: dict[str, Any] = {}

        if hard_filters.brand:
            brand_filter["name"] = Store._insensitive_contains(hard_filters.brand)

        if hard_filters.category:
            brand_filter["category"] = Store._insensitive_contains(hard_filters.category)

        if include_subcategory and hard_filters.subcategory:
            brand_filter["subcategory"] = Store._insensitive_contains(
                hard_filters.subcategory,
            )

        return brand_filter

    @staticmethod
    def _insensitive_contains(value: str) -> dict[str, str]:
        """Filter string không phân biệt hoa thường."""
        return {"contains": value.strip(), "mode": "insensitive"}

    @staticmethod
    def _extract_opening_hours_preference(
        signals: list[RankingSignalItem],
    ) -> OpeningHoursPreference | None:
        """Lấy ràng buộc giờ mở cửa từ signal có confidence cao nhất."""
        candidates = [
            item
            for item in signals
            if item.signal == RankingSignalType.OPENING_HOURS and item.opening_hours
        ]
        if not candidates:
            return None

        best = max(candidates, key=lambda item: item.confidence)
        return best.opening_hours
