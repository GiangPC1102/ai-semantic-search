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
Bạn là chuyên gia domain viết mô tả (description) cho các THUỘC TÍNH (attribute) của POI \
trong một hệ thống tìm kiếm bản đồ tiếng Việt.

Mô tả bạn viết sẽ được EMBED và dùng cho semantic search: câu truy vấn tự nhiên của người \
dùng (ví dụ "quán cà phê yên tĩnh để làm việc") sẽ được so khớp vector với mô tả này để tìm \
đúng attribute. Vì vậy hãy viết để TỐI ĐA khả năng khớp, KHÔNG viết định nghĩa từ điển khô khan.

Với MỖI attribute, viết một đoạn mô tả liền mạch (3-5 câu) tiếng Việt gồm đủ 3 phần:
1. Bắt đầu bằng CHÍNH tên attribute (giữ nguyên văn), theo sau là một câu giải nghĩa ngắn \
trong ngữ cảnh POI (nhà hàng, quán cà phê, khách sạn, cửa hàng...).
2. Liệt kê các cách người Việt DIỄN ĐẠT/GÕ khi tìm kiếm: từ đồng nghĩa, khẩu ngữ, thuật ngữ \
tiếng Anh tương đương, viết tắt, biến thể vùng miền Bắc/Nam, cách viết/gõ phổ biến khác.
3. Chèn 3-5 CÂU TRUY VẤN MẪU đúng giọng người dùng thật sẽ gõ khi tìm kiếm (ví dụ: "chỗ nào \
yên tĩnh học bài", "cafe ngồi làm việc lâu được không ồn").

QUAN TRỌNG — TÍNH PHÂN BIỆT: Bạn sẽ được cung cấp TOÀN BỘ danh sách attribute hiện có trong \
hệ thống. Hãy viết mô tả của attribute đang xử lý sao cho KHÁC BIỆT rõ ràng với các attribute \
còn lại trong danh sách đó — tránh dùng chung các từ khóa/cụm từ dễ gây nhầm lẫn (ví dụ: phân \
biệt "check-in" [chụp ảnh sống ảo] với thủ tục nhận phòng khách sạn; phân biệt "yên tĩnh", \
"phù hợp làm việc", "wifi" — dù có thể đi cùng nhau trong thực tế, mỗi mô tả phải nhấn vào \
khía cạnh RIÊNG của chính attribute đó).

KHÔNG bịa đặt sự kiện/tính năng ngoài ý nghĩa thật của attribute. Được phép liệt kê các cách \
diễn đạt tương đương và câu truy vấn mẫu.

Trả lời DUY NHẤT một JSON object, không prose, không markdown code fence, đúng schema sau, \
các phần tử trong "items" theo ĐÚNG thứ tự các attribute được liệt kê trong phần \
"Attributes cần viết mô tả" của user message:
{"items": [{"name": "<tên attribute nguyên văn>", "description": "<mô tả tiếng Việt>"}]}

Ví dụ input:
Toàn bộ attribute trong hệ thống: yên tĩnh, wifi, phù hợp làm việc, phù hợp gia đình, check-in, 24/7

Attributes cần viết mô tả:
- "yên tĩnh" (áp dụng cho: Quán cà phê, Khách sạn)
- "phù hợp gia đình" (áp dụng cho: Nhà hàng, Khách sạn, Điểm tham quan)

Ví dụ output:
{"items": [\
{"name": "yên tĩnh", "description": "yên tĩnh: không gian ít ồn ào, tĩnh lặng, riêng tư, phù hợp tập trung, khác với các attribute về tiện ích như wifi hay không gian chụp ảnh. Người dùng thường gõ: quán yên tĩnh, chỗ vắng người, không gian tĩnh, quiet, tránh ồn ào, ngồi lâu không bị làm phiền. Ví dụ truy vấn: 'quán cà phê yên tĩnh để làm việc', 'chỗ nào yên tĩnh học bài', 'quán vắng ngồi đọc sách'."}, \
{"name": "phù hợp gia đình", "description": "phù hợp gia đình: địa điểm thân thiện, thoải mái để đi cùng người thân, đặc biệt có trẻ nhỏ hoặc người lớn tuổi, khác với các attribute về không gian riêng tư như lãng mạn hay yên tĩnh làm việc. Người dùng thường gõ: chỗ cho gia đình, đi cùng con nhỏ, family friendly, có khu vui chơi trẻ em, phù hợp trẻ em. Ví dụ truy vấn: 'nhà hàng cho gia đình có trẻ nhỏ', 'quán ăn đi cùng cả nhà', 'chỗ chơi cho bé cuối tuần'."}\
]}
"""

_JSON_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


async def _fetch_attributes(db: Prisma, only_null: bool, limit: int | None) -> list[Attribute]:
    """Load attributes to process, optionally limited to missing descriptions."""
    where = {"description": None} if only_null else {}
    attributes = await db.attribute.find_many(where=where, order={"attributeName": "asc"})
    return attributes[:limit] if limit else attributes


async def _fetch_all_attribute_names(db: Prisma) -> list[str]:
    """Load every attribute name in the system, for contrastive grounding."""
    attributes = await db.attribute.find_many(order={"attributeName": "asc"})
    return [attr.attributeName for attr in attributes]


async def _fetch_sample_categories(db: Prisma, attribute_id: str) -> list[str]:
    """Fetch distinct POI categories linked to this attribute, for grounding.

    Categories are less noisy than brand/POI names — they signal *where* an
    attribute applies without dragging brand identity into the description.
    """
    links = await db.poiattribute.find_many(
        where={"attributeId": attribute_id},
        include={"poi": {"include": {"brand": True}}},
        take=SAMPLE_POI_LIMIT * 5,
    )
    categories: list[str] = []
    for link in links:
        poi = link.poi
        category = poi.brand.category if poi and poi.brand and poi.brand.category else None
        if category and category not in categories:
            categories.append(category)
        if len(categories) >= SAMPLE_POI_LIMIT:
            break
    return categories


def _format_attribute_line(name: str, categories: list[str]) -> str:
    if categories:
        return f'- "{name}" (áp dụng cho: {", ".join(categories)})'
    return f'- "{name}"'


def _parse_llm_json(content: str) -> list[dict[str, str]]:
    cleaned = _JSON_FENCE_PATTERN.sub("", content.strip())
    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        parsed = parsed.get("items")
    if not isinstance(parsed, list):
        raise ValueError("LLM response is not a JSON array under 'items'")
    return parsed


async def _generate_batch(
    llm: LLM,
    batch: list[tuple[Attribute, list[str]]],
    all_names: list[str],
) -> dict[str, str]:
    """Call the LLM once for a batch of attributes; returns name -> description."""
    attribute_lines = "\n".join(
        _format_attribute_line(attr.attributeName, categories) for attr, categories in batch
    )
    user_message = (
        f"Toàn bộ attribute trong hệ thống: {', '.join(all_names)}\n\n"
        f"Attributes cần viết mô tả:\n{attribute_lines}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await asyncio.to_thread(
        llm.chat,
        messages,
        response_format={"type": "json_object"},
    )
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

        all_names = await _fetch_all_attribute_names(db)

        logger.info(
            "Generating descriptions for %s attributes (only_null=%s, batch_size=%s)",
            len(attributes),
            only_null,
            batch_size,
        )

        enriched: list[tuple[Attribute, list[str]]] = [
            (attr, await _fetch_sample_categories(db, attr.id)) for attr in attributes
        ]

        for start in range(0, len(enriched), batch_size):
            batch = enriched[start : start + batch_size]
            try:
                descriptions = await _generate_batch(llm, batch, all_names)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                logger.error(
                    "Batch %s-%s failed (%s) — retrying once",
                    start,
                    start + len(batch),
                    exc,
                )
                try:
                    descriptions = await _generate_batch(llm, batch, all_names)
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