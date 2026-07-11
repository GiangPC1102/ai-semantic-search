"""Generate Vietnamese descriptions for POI attributes via LLM (OpenAI by default).

Attribute descriptions are embedded into Qdrant ``attribute_data`` for semantic
attribute search (see ``ingest_attribute_vectors.py``) — a missing or thin
description makes that attribute invisible to search. Run this after Phase 4
of ``ingest_poi_data.py`` and before ``ingest_attribute_vectors.py``:

    python -m app.scripts.generate_attribute_descriptions
    python -m app.scripts.ingest_attribute_vectors

By default every attribute is (re)generated so wording stays consistent across
the whole taxonomy. Use ``--only-null`` to limit the run to attributes that
have no description yet.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re

from prisma import Prisma
from prisma.models import Attribute

from app.core.logger import logger
from app.utils.llm_partern import LLM, LLMError

DEFAULT_BATCH_SIZE = 25
SAMPLE_POI_LIMIT = 3

SYSTEM_PROMPT = """\
You are a domain expert writing attribute descriptions for a Vietnamese \
point-of-interest (POI) map search engine. For every attribute name given, \
write ONE to TWO sentences IN VIETNAMESE that:
- explain what the attribute means in the context of a POI (restaurant, cafe, \
shop, hotel, etc.)
- weave in natural synonyms and phrasings a Vietnamese user might type when \
searching (alternate wording, colloquial terms), not just a dictionary definition

These descriptions are embedded and used for semantic search, so favor rich, \
search-friendly phrasing over a dry definition. Do not invent facts beyond the \
attribute name and the example POIs given.

Reply with ONLY a JSON array, no prose, no markdown code fence, matching this \
schema exactly, one object per attribute in the same order as the input:
[{"name": "<attribute name exactly as given>", "description": "<Vietnamese description>"}]

Example input:
- "có wifi miễn phí" (ví dụ POI: Highlands Coffee [Cafe], The Coffee House [Cafe])
- "phù hợp gia đình" (ví dụ POI: Pizza 4P's [Nhà hàng], Vincom Mega Mall [Trung tâm thương mại])

Example output:
[{"name": "có wifi miễn phí", "description": "Địa điểm cung cấp wifi miễn phí cho khách, phù hợp khi tìm quán có mạng, wifi free, internet không tính phí để làm việc hoặc học tập."}, \
{"name": "phù hợp gia đình", "description": "Địa điểm thân thiện với gia đình có trẻ nhỏ, phù hợp đi cùng con cái, không gian rộng rãi, thoải mái cho các buổi họp mặt gia đình hoặc đi chơi cuối tuần."}]
"""

_JSON_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


async def _fetch_attributes(db: Prisma, only_null: bool, limit: int | None) -> list[Attribute]:
    """Load attributes to process, optionally limited to missing descriptions."""
    where = {"description": None} if only_null else {}
    attributes = await db.attribute.find_many(where=where, order={"attributeName": "asc"})
    return attributes[:limit] if limit else attributes


async def _fetch_sample_poi_labels(db: Prisma, attribute_id: str) -> list[str]:
    """Fetch a few POI names (with category) linked to this attribute, for grounding."""
    links = await db.poiattribute.find_many(
        where={"attributeId": attribute_id},
        include={"poi": {"include": {"brand": True}}},
        take=SAMPLE_POI_LIMIT,
    )
    labels: list[str] = []
    for link in links:
        poi = link.poi
        if poi is None:
            continue
        category = poi.brand.category if poi.brand and poi.brand.category else None
        labels.append(f"{poi.name} [{category}]" if category else poi.name)
    return labels


def _format_attribute_line(name: str, samples: list[str]) -> str:
    if samples:
        return f'- "{name}" (ví dụ POI: {", ".join(samples)})'
    return f'- "{name}"'


def _parse_llm_json(content: str) -> list[dict[str, str]]:
    cleaned = _JSON_FENCE_PATTERN.sub("", content.strip())
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("LLM response is not a JSON array")
    return parsed


async def _generate_batch(
    llm: LLM,
    batch: list[tuple[Attribute, list[str]]],
) -> dict[str, str]:
    """Call the LLM once for a batch of attributes; returns name -> description."""
    user_message = "\n".join(
        _format_attribute_line(attr.attributeName, samples) for attr, samples in batch
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await asyncio.to_thread(llm.chat, messages)
    items = _parse_llm_json(response.content)

    result: dict[str, str] = {}
    for item in items:
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if name and description:
            result[name] = description
    return result


async def generate_attribute_descriptions(
    only_null: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
) -> int:
    """Generate and persist LLM-written descriptions for POI attributes.

    Args:
        only_null: Only process attributes whose description is currently null.
        batch_size: Number of attributes sent to the LLM per call.
        limit: Cap the number of attributes processed (useful for a dry run).

    Returns:
        Number of attributes updated with a new description.
    """
    db = Prisma()
    llm = LLM()
    updated_count = 0

    await db.connect()
    try:
        attributes = await _fetch_attributes(db, only_null, limit)
        if not attributes:
            logger.warning("No attribute to process — nothing to generate")
            return 0

        logger.info(
            "Generating descriptions for %s attributes (only_null=%s, batch_size=%s)",
            len(attributes),
            only_null,
            batch_size,
        )

        enriched: list[tuple[Attribute, list[str]]] = [
            (attr, await _fetch_sample_poi_labels(db, attr.id)) for attr in attributes
        ]

        for start in range(0, len(enriched), batch_size):
            batch = enriched[start : start + batch_size]
            try:
                descriptions = await _generate_batch(llm, batch)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                logger.error(
                    "Batch %s-%s failed (%s) — retrying once",
                    start,
                    start + len(batch),
                    exc,
                )
                try:
                    descriptions = await _generate_batch(llm, batch)
                except (LLMError, ValueError, json.JSONDecodeError) as retry_exc:
                    logger.error(
                        "Batch %s-%s failed again, skipping (%s)",
                        start,
                        start + len(batch),
                        retry_exc,
                    )
                    continue

            for attr, _samples in batch:
                description = descriptions.get(attr.attributeName)
                if not description:
                    logger.warning("No description returned for %r", attr.attributeName)
                    continue
                await db.attribute.update(
                    where={"id": attr.id},
                    data={"description": description},
                )
                updated_count += 1

            logger.info("Progress: %s/%s attributes updated", updated_count, len(enriched))

        logger.info("Done: %s/%s attributes updated", updated_count, len(enriched))
        return updated_count
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only-null",
        action="store_true",
        help="Only generate descriptions for attributes that currently have none.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of attributes processed (useful to try a small batch first).",
    )
    args = parser.parse_args()

    count = asyncio.run(
        generate_attribute_descriptions(
            only_null=args.only_null,
            batch_size=args.batch_size,
            limit=args.limit,
        )
    )
    print(f"Updated {count} attribute description(s)")


if __name__ == "__main__":
    main()
