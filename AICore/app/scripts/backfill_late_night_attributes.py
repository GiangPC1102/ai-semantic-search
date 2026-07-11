"""Backfill "mở khuya"/"mở muộn" attribute links from real ``open_hours`` data.

``is_filter_attribute`` (see ``app.services.tasco_search``) filters POIs purely
by which ``Attribute`` rows are already linked via ``poi_attributes`` — it never
re-reads ``open_hours`` at query time. So a POI that genuinely closes late but
was never tagged with "mở khuya"/"mở muộn" in the source dataset stays
invisible to that filter. This script derives the tag from the real
``open_hours`` field instead of relying on the original manual tagging.

Rule: a POI counts as "mở khuya"/"mở muộn" iff it is 24/7, its schedule crosses
midnight, or its close time is after 22:00 (strict) — matches the description
rule already embedded on both attributes (see
``app.scripts.generate_attribute_descriptions.MANDATORY_RULE_SUFFIXES``).

Idempotent: only creates links that don't already exist.

    python -m app.scripts.backfill_late_night_attributes
"""

from __future__ import annotations

import asyncio

from prisma import Prisma
from prisma.models import Poi

from app.core.logger import logger
from app.helpers.opening_hours_matcher import ParsedOpenHours, parse_open_hours

LATE_NIGHT_THRESHOLD_MINUTES = 22 * 60
TARGET_ATTRIBUTE_NAMES = ("mở khuya", "mở muộn")


def _closes_late(schedule: ParsedOpenHours) -> bool:
    """True nếu 24/7, vắt qua nửa đêm, hoặc đóng cửa sau 22:00 (strict)."""
    if schedule.is_24h or schedule.open_minutes == schedule.close_minutes:
        return True
    if schedule.close_minutes < schedule.open_minutes:
        return True
    return schedule.close_minutes > LATE_NIGHT_THRESHOLD_MINUTES


def _find_late_poi_ids(pois: list[Poi]) -> list[str]:
    late_poi_ids: list[str] = []
    for poi in pois:
        if not poi.openHours:
            continue
        schedule = parse_open_hours(poi.openHours)
        if schedule is not None and _closes_late(schedule):
            late_poi_ids.append(poi.id)
    return late_poi_ids


async def backfill_late_night_attributes(db: Prisma | None = None) -> dict[str, int]:
    """Link every late-closing POI to the "mở khuya"/"mở muộn" attributes.

    Args:
        db: Reuse an already-connected client (e.g. when called from
            ``generate_attribute_descriptions``) instead of opening a new one.

    Returns:
        Mapping attribute name -> number of new ``poi_attributes`` rows created.
    """
    owns_db = db is None
    if owns_db:
        db = Prisma()
        await db.connect()
    try:
        attributes = {}
        for name in TARGET_ATTRIBUTE_NAMES:
            attr = await db.attribute.find_first(where={"attributeName": name})
            if attr is None:
                raise RuntimeError(
                    f"Attribute {name!r} not found — run generate_attribute_descriptions first"
                )
            attributes[name] = attr

        pois = await db.poi.find_many()
        late_poi_ids = _find_late_poi_ids(pois)
        logger.info("Found %s/%s POI closing after 22:00", len(late_poi_ids), len(pois))

        created_counts: dict[str, int] = {}
        for name, attr in attributes.items():
            existing_links = await db.poiattribute.find_many(where={"attributeId": attr.id})
            existing_poi_ids = {link.poiId for link in existing_links}
            missing_poi_ids = [pid for pid in late_poi_ids if pid not in existing_poi_ids]

            for poi_id in missing_poi_ids:
                await db.poiattribute.create(data={"poiId": poi_id, "attributeId": attr.id})

            created_counts[name] = len(missing_poi_ids)
            logger.info(
                "%s: +%s new link(s) (had %s, target %s)",
                name,
                len(missing_poi_ids),
                len(existing_poi_ids),
                len(late_poi_ids),
            )

        return created_counts
    finally:
        if owns_db:
            await db.disconnect()


def main() -> None:
    counts = asyncio.run(backfill_late_night_attributes())
    for name, count in counts.items():
        print(f"{name}: +{count} POI-attribute link(s) created")


if __name__ == "__main__":
    main()
