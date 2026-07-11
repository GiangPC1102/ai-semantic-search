"""Nạp dữ liệu POI dataset cố định (hard-coded) vào PostgreSQL qua Prisma.

Dữ liệu lấy từ app/scripts/poi_seed_data.py (đã export sẵn từ file Excel gốc
`data/ai_maps_track2_dataset_participants.xlsx`, sheet POI_Dataset + Attribute_Taxonomy)
nên không cần đọc Excel khi ingest/seed database nữa.

Chạy theo phase độc lập (mỗi phase idempotent, có thể chạy lại):
    Phase 2 — seed dữ liệu tham chiếu: signals (từ RankingSignalType) + attribute taxonomy gốc.
    Phase 3 — ingest POI core: brands + poi.
    Phase 4 — ingest quan hệ: poi_attributes + poi_tags.

Phase 1 (thêm @@unique + tạo bảng) không nằm trong file này — chạy trước bằng
`prisma migrate deploy` / `prisma generate`.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import unicodedata
from typing import Any

from prisma import Prisma
from prisma.fields import Json

from app.core.logger import logger
from app.scripts.poi_seed_data import POI_DATASET

_RANGE_PATTERN = re.compile(r"^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$")
_24H_MARKERS = ("24/7", "24h", "24 giờ", "cả ngày")

SIGNAL_DESCRIPTIONS: dict[str, str] = {
    "mixed_language": "Xử lý truy vấn đa ngôn ngữ (Việt-Anh) trong ranking",
    "opening_hours": "Khớp giờ mở cửa với yêu cầu thời gian trong truy vấn",
    "price": "Xếp hạng theo mức giá (price_level)",
    "popularity": "Mức phổ biến dựa trên lượt tìm kiếm, review hoặc độ nhận diện",
    "location": "Khoảng cách hoặc vị trí địa lý so với tham chiếu trong truy vấn",
    "category": "Lọc và xếp hạng theo loại POI (category/sub_category)",
    "attribute": "Ràng buộc truy vấn phải khớp một thuộc tính cụ thể của POI",
    "attributes": "Ràng buộc truy vấn phải khớp đồng thời nhiều thuộc tính cụ thể của POI",
    "semantic": "Khớp ngữ nghĩa và intent của truy vấn với mô tả POI",
    "rating": "Điểm đánh giá người dùng của POI",
    "review": "Tín hiệu khai thác từ review, tags hoặc phản hồi người dùng",
}

# English names for attributes in Attribute_Taxonomy sheet.
ATTRIBUTE_ENGLISH_NAMES: dict[str, str] = {
    "yên tĩnh": "quiet",
    "wifi": "wifi",
    "phù hợp làm việc": "work-friendly",
    "phù hợp gia đình": "family-friendly",
    "lãng mạn": "romantic",
    "mở khuya": "open late",
    "gần biển": "near the beach",
    "bãi đỗ xe": "parking",
    "check-in": "check-in",
    "24/7": "24/7",
}


def _normalize_token(value: str) -> str:
    """Unicode NFC + strip + collapse whitespace — dùng cho attribute/tag."""
    cleaned = unicodedata.normalize("NFC", value).strip()
    return re.sub(r"\s+", " ", cleaned)


def _clean(value: Any) -> str | None:
    """None/NaN/'' -> None; ngược lại trả chuỗi đã strip."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def _parse_opening_hours(raw: Any) -> dict[str, Any]:
    """Chuẩn hoá 'HH:MM-HH:MM' / '24/7' thành dict cho cột Poi.openHours.

    Format khớp ``app.helpers.opening_hours_matcher._parse_open_hours_dict``.
    """
    cleaned = _clean(raw)
    if cleaned is None:
        return {"is_24h": False}

    lowered = cleaned.lower()
    if any(marker in lowered for marker in _24H_MARKERS):
        return {"is_24h": True}

    match = _RANGE_PATTERN.match(cleaned)
    if not match:
        logger.warning("Không parse được opening_hours: %r", raw)
        return {"is_24h": False}

    return {"open_time": match.group(1), "close_time": match.group(2), "is_24h": False}


def _split_multi(raw: Any) -> list[str]:
    """Split cột attributes/tags (';'-separated) và chuẩn hoá từng token."""
    cleaned = _clean(raw)
    if cleaned is None:
        return []
    return [t for t in (_normalize_token(x) for x in cleaned.split(";")) if t]


# ---------------------------------------------------------------------------
# Phase 2 — seed dữ liệu tham chiếu (không phụ thuộc POI)
# ---------------------------------------------------------------------------


async def seed_signals(db: Prisma) -> int:
    """Upsert 11 giá trị RankingSignalType vào bảng `signals`."""
    for name, description in SIGNAL_DESCRIPTIONS.items():
        await db.signal.upsert(
            where={"signalName": name},
            data={
                "create": {"signalName": name, "description": description},
                "update": {"description": description},
            },
        )
    logger.info("Phase 2: seeded %s signals", len(SIGNAL_DESCRIPTIONS))
    return len(SIGNAL_DESCRIPTIONS)


async def seed_attribute_taxonomy(db: Prisma) -> int:
    """Upsert attribute taxonomy gốc từ trường `attributes` (';'-separated) của POI_DATASET."""
    names: set[str] = set()
    for row in POI_DATASET:
        names.update(_split_multi(row.get("attributes")))

    count = 0
    for name in sorted(names):
        await db.attribute.upsert(
            where={"attributeName": name},
            data={"create": {"attributeName": name}, "update": {}},
        )
        count += 1
    logger.info("Phase 2: seeded %s attributes từ POI_DATASET", count)
    return count


async def run_phase_2(db: Prisma) -> None:
    await seed_signals(db)
    await seed_attribute_taxonomy(db)


# ---------------------------------------------------------------------------
# Phase 3 — ingest POI core (brand + poi)
# ---------------------------------------------------------------------------


async def ingest_poi_core(db: Prisma) -> tuple[int, int]:
    """Upsert brands + poi. Không xử lý attributes/tags (xem Phase 4)."""
    brand_cache: dict[str, str] = {}
    poi_count = 0
    brand_count = 0

    for row in POI_DATASET:
        brand_name = _clean(row.get("brand"))
        brand_id: str | None = None
        if brand_name:
            if brand_name not in brand_cache:
                brand = await db.brand.upsert(
                    where={"name": brand_name},
                    data={
                        "create": {
                            "name": brand_name,
                            "category": _clean(row.get("category")),
                            "subcategory": _clean(row.get("sub_category")),
                        },
                        # Tie-break: giữ category/subcategory ghi nhận lần đầu.
                        "update": {},
                    },
                )
                brand_cache[brand_name] = brand.id
                brand_count += 1
            brand_id = brand_cache[brand_name]

        poi_id = row["poi_id"].strip()
        latitude = _clean(row.get("latitude"))
        longitude = _clean(row.get("longitude"))
        rating = _clean(row.get("rating"))
        review_count = _clean(row.get("review_count"))
        popularity_score = _clean(row.get("popularity_score"))

        poi_data: dict[str, Any] = {
            "name": row["poi_name"].strip(),
            "city": _clean(row.get("city")),
            "district": _clean(row.get("district")),
            "address": _clean(row.get("address")),
            "latitude": float(latitude) if latitude else None,
            "longitude": float(longitude) if longitude else None,
            "rating": float(rating) if rating else None,
            "reviewCount": int(float(review_count)) if review_count else None,
            "popularityScore": float(popularity_score) if popularity_score else None,
            # Poi.priceLevel là String? — ép str (không để nguyên số).
            "priceLevel": _clean(row.get("price_level")),
            # Json field cần wrap bằng prisma.fields.Json, không truyền dict trần.
            "openHours": Json(_parse_opening_hours(row.get("opening_hours"))),
            "description": _clean(row.get("description")),
        }
        # brandId là scalar FK ẩn — client chỉ chấp nhận set qua relation `brand.connect`.
        if brand_id:
            poi_data["brand"] = {"connect": {"id": brand_id}}

        await db.poi.upsert(
            where={"id": poi_id},
            data={"create": {"id": poi_id, **poi_data}, "update": poi_data},
        )
        poi_count += 1

    logger.info("Phase 3: ingested %s poi, %s brand", poi_count, brand_count)
    return poi_count, brand_count


# ---------------------------------------------------------------------------
# Phase 4 — ingest quan hệ POI (attributes & tags)
# ---------------------------------------------------------------------------


async def ingest_poi_relations(db: Prisma) -> tuple[int, int]:
    """Ingest poi_attributes + poi_tags (tự tạo attribute/tag mới nếu chưa có)."""
    attribute_cache: dict[str, str] = {}
    tag_cache: dict[str, str] = {}
    attr_links = 0
    tag_links = 0

    for row in POI_DATASET:
        poi_id = row["poi_id"].strip()

        for attr_name in _split_multi(row.get("attributes")):
            if attr_name not in attribute_cache:
                english_name = ATTRIBUTE_ENGLISH_NAMES.get(attr_name)
                attribute = await db.attribute.upsert(
                    where={"attributeName": attr_name},
                    data={
                        "create": {
                            "attributeName": attr_name,
                            "englishName": english_name,
                        },
                        "update": {"englishName": english_name},
                    },
                )
                attribute_cache[attr_name] = attribute.id
            await db.poiattribute.upsert(
                where={
                    "poiId_attributeId": {
                        "poiId": poi_id,
                        "attributeId": attribute_cache[attr_name],
                    }
                },
                data={
                    "create": {"poiId": poi_id, "attributeId": attribute_cache[attr_name]},
                    "update": {},
                },
            )
            attr_links += 1

        for tag_name in _split_multi(row.get("tags")):
            if tag_name not in tag_cache:
                tag = await db.tag.upsert(
                    where={"name": tag_name},
                    data={"create": {"name": tag_name}, "update": {}},
                )
                tag_cache[tag_name] = tag.id
            await db.poitag.upsert(
                where={"poiId_tagId": {"poiId": poi_id, "tagId": tag_cache[tag_name]}},
                data={"create": {"poiId": poi_id, "tagId": tag_cache[tag_name]}, "update": {}},
            )
            tag_links += 1

    logger.info(
        "Phase 4: %s poi_attributes links, %s poi_tags links, %s distinct attributes, %s distinct tags",
        attr_links,
        tag_links,
        len(attribute_cache),
        len(tag_cache),
    )
    return attr_links, tag_links


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_ingest(phase: str) -> None:
    """Run one or all ingest phases (2/3/4/all). Manages its own DB connection."""
    db = Prisma()
    await db.connect()
    try:
        if phase in ("2", "all"):
            await run_phase_2(db)
        if phase in ("3", "all"):
            await ingest_poi_core(db)
        if phase in ("4", "all"):
            await ingest_poi_relations(db)
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["2", "3", "4", "all"], default="all")
    args = parser.parse_args()

    asyncio.run(run_ingest(args.phase))


if __name__ == "__main__":
    main()
