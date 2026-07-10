"""Đọc file Excel POI dataset và nạp dữ liệu vào PostgreSQL qua Prisma.

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
from pathlib import Path
from typing import Any

import pandas as pd
from prisma import Prisma
from prisma.fields import Json

from app.core.logger import logger

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_XLSX = WORKSPACE_ROOT / "data" / "ai_maps_track2_dataset_participants.xlsx"
DEFAULT_POI_SHEET = "POI_Dataset"
DEFAULT_ATTRIBUTE_SHEET = "Attribute_Taxonomy"

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


async def seed_attribute_taxonomy(db: Prisma, file: Path, sheet: str) -> int:
    """Upsert attribute taxonomy gốc từ sheet Attribute_Taxonomy."""
    df = pd.read_excel(file, sheet_name=sheet, dtype=str)
    count = 0
    for _, row in df.iterrows():
        name = _normalize_token(row["attribute"])
        description = _clean(row.get("semantic_meaning"))
        await db.attribute.upsert(
            where={"attributeName": name},
            data={
                "create": {"attributeName": name, "description": description},
                "update": {"description": description},
            },
        )
        count += 1
    logger.info("Phase 2: seeded %s attributes từ taxonomy", count)
    return count


async def run_phase_2(db: Prisma, file: Path, attribute_sheet: str) -> None:
    await seed_signals(db)
    await seed_attribute_taxonomy(db, file, attribute_sheet)


# ---------------------------------------------------------------------------
# Phase 3 — ingest POI core (brand + poi)
# ---------------------------------------------------------------------------


async def ingest_poi_core(db: Prisma, file: Path, sheet: str) -> tuple[int, int]:
    """Upsert brands + poi. Không xử lý attributes/tags (xem Phase 4)."""
    df = pd.read_excel(file, sheet_name=sheet, dtype=str)
    brand_cache: dict[str, str] = {}
    poi_count = 0
    brand_count = 0

    for _, row in df.iterrows():
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


async def ingest_poi_relations(db: Prisma, file: Path, sheet: str) -> tuple[int, int]:
    """Ingest poi_attributes + poi_tags (tự tạo attribute/tag mới nếu chưa có)."""
    df = pd.read_excel(file, sheet_name=sheet, dtype=str)
    attribute_cache: dict[str, str] = {}
    tag_cache: dict[str, str] = {}
    attr_links = 0
    tag_links = 0

    for _, row in df.iterrows():
        poi_id = row["poi_id"].strip()

        for attr_name in _split_multi(row.get("attributes")):
            if attr_name not in attribute_cache:
                attribute = await db.attribute.upsert(
                    where={"attributeName": attr_name},
                    data={"create": {"attributeName": attr_name}, "update": {}},
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


async def _run(phase: str, file: Path, poi_sheet: str, attribute_sheet: str) -> None:
    db = Prisma()
    await db.connect()
    try:
        if phase in ("2", "all"):
            await run_phase_2(db, file, attribute_sheet)
        if phase in ("3", "all"):
            await ingest_poi_core(db, file, poi_sheet)
        if phase in ("4", "all"):
            await ingest_poi_relations(db, file, poi_sheet)
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_INPUT_XLSX)
    parser.add_argument("--poi-sheet", default=DEFAULT_POI_SHEET)
    parser.add_argument("--attribute-sheet", default=DEFAULT_ATTRIBUTE_SHEET)
    parser.add_argument("--phase", choices=["2", "3", "4", "all"], default="all")
    args = parser.parse_args()

    asyncio.run(_run(args.phase, args.file, args.poi_sheet, args.attribute_sheet))


if __name__ == "__main__":
    main()
