"""Generate Vietnamese descriptions for POI attributes via LLM (OpenAI by default).

Attribute descriptions are embedded into Qdrant ``attribute_data`` for semantic
attribute search (see ``ingest_attribute_vectors.py``) — a missing, thin, or
ambiguous description makes that attribute invisible (or mismatched) at search
time. Run this after Phase 4 of ``ingest_poi_data.py`` and before
``ingest_attribute_vectors.py``:

    python -m app.scripts.generate_attribute_descriptions
    python -m app.scripts.ingest_attribute_vectors
    
By default every attribute is (re)generated so wording stays consistent across
the whole taxonomy. Use ``--only-null`` to limit the run to attributes that
have no description yet.

Two techniques ground the LLM so ambiguous names (e.g. "check-in" — photo spot
vs. hotel check-in) resolve to their *actual* meaning in this dataset instead
of a dictionary guess:

1. Grounding: each attribute is shown real POI descriptions of the POIs it is
   attached to (not just categories) — the LLM writes from evidence.
2. Contrastive batching: attribute names are embedded (bge-m3) and clustered
   (Agglomerative, cosine distance, threshold ~0.25) into near-synonym groups,
   plus a per-item k-NN of hard negatives. Each LLM call is packed
   cluster-by-cluster (never splitting a cluster across calls) and told which
   sibling names to differentiate from. Crucially the OUTPUT stays positive —
   it never names or negates a sibling, because the whole string is embedded
   and a vector model would otherwise import the sibling's keywords (even under
   "không phải…") and mis-attract that sibling's queries. The contrast list
   only steers the LLM's *word choice*; it must not leak into the text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

import numpy as np
import pandas as pd
from prisma import Prisma
from prisma.models import Attribute
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.core.logger import logger
from app.grpc.embedding.embedding_client import EmbeddingServiceClient
from app.utils.llm_partern import LLM, LLMError

DEFAULT_BATCH_SIZE = 25
DEFAULT_SAMPLES_PER_ATTR = 6
DEFAULT_CLUSTER_DISTANCE_THRESHOLD = 0.25
DEFAULT_KNN_NEIGHBORS = 5
MAX_CONTRAST_NAMES = 8

# Vietnamese display names for ranking signals — curated, matches RankingSignalType enum.
SIGNAL_VIETNAM_NAMES: dict[str, str] = {
    "mixed_language": "Đa ngôn ngữ",
    "opening_hours": "Giờ mở cửa",
    "price": "Giá",
    "popularity": "Phổ biến",
    "location": "Vị trí",
    "category": "Loại hình",
    "attribute": "Thuộc tính",
    "attributes": "Nhiều thuộc tính",
    "semantic": "Ngữ nghĩa",
    "rating": "Đánh giá",
    "review": "Nhận xét",
}

SYSTEM_PROMPT = """\
Bạn là chuyên gia domain viết mô tả (description) NGẮN GỌN cho các THUỘC TÍNH (attribute) của \
POI trong một hệ thống tìm kiếm bản đồ tiếng Việt.

Mô tả bạn viết sẽ được EMBED thành vector và dùng cho semantic search: câu truy vấn tự nhiên \
của người dùng (ví dụ "quán cà phê yên tĩnh để làm việc") được so khớp vector với mô tả này để \
tìm đúng attribute. Viết để TỐI ĐA khả năng khớp, ngắn gọn, KHÔNG viết định nghĩa từ điển dài dòng.

QUY TẮC TỐI QUAN TRỌNG (vì văn bản này sẽ bị embed thành vector):
- Chỉ mô tả attribute này LÀ GÌ bằng chính từ khóa ĐẶC TRƯNG của nó, viết TÍCH CỰC.
- TUYỆT ĐỐI KHÔNG dùng phủ định ("không phải…", "khác với…", "chứ không…") và KHÔNG nhắc \
tên hay từ khóa của bất kỳ attribute nào trong danh sách "cần phân biệt rõ với". Lý do: mô hình \
vector BỎ QUA phủ định, nên một câu chứa từ khóa của attribute khác sẽ HÚT NHẦM truy vấn về \
attribute đó — phản tác dụng.
- Danh sách "cần phân biệt rõ với" CHỈ để bạn CHỌN từ ngữ đặc trưng riêng, viết sao cho mô tả \
không trùng lặp với chúng. Bản thân các tên/từ khóa đó KHÔNG được xuất hiện trong output.

Với MỖI attribute bạn được cung cấp:
- Danh mục POI mà attribute áp dụng (nếu có).
- MỘT VÀI MÔ TẢ POI THẬT có gắn attribute này — đây là NGUỒN SỰ THẬT về nghĩa thực tế của \
attribute trong dataset; hãy bám sát nó thay vì suy diễn nghĩa từ điển. (Ví dụ "check-in" trong \
dataset này chỉ mang nghĩa chụp ảnh sống ảo/điểm tham quan, nên chỉ viết theo nghĩa đó.)
- Danh sách "cần phân biệt rõ với" — các attribute gần nghĩa nhất (xem quy tắc trên).

Với MỖI attribute, trả về:
1. "gloss": MỘT câu ngắn (5-15 từ), tích cực, nêu đúng và đặc trưng nhất nghĩa của attribute \
trong dataset này.
2. "synonyms": các cách người Việt DIỄN ĐẠT/GÕ khi tìm kiếm (từ đồng nghĩa, khẩu ngữ, thuật ngữ \
tiếng Anh tương đương, viết tắt, biến thể Bắc/Nam), ngăn cách bằng dấu phẩy. Chỉ gồm từ khóa \
của CHÍNH attribute này.
3. "queries": mảng 2-3 CÂU TRUY VẤN MẪU đúng giọng người dùng thật sẽ gõ khi tìm kiếm.
4. "englishName": nhãn tiếng Anh NGẮN GỌN cho attribute (lowercase, nối từ bằng dấu gạch \
ngang, ví dụ "work-friendly", "near-the-beach"), dịch đúng ý nghĩa đã xác định ở "gloss".

KHÔNG bịa tính năng ngoài nghĩa thật của attribute — chỉ dùng các mô tả POI thật làm căn cứ.

Trả lời DUY NHẤT một JSON object, không prose, không markdown code fence, đúng schema sau, các \
phần tử trong "items" theo ĐÚNG thứ tự attribute trong phần "Attributes cần viết mô tả" của \
user message:
{"items": [{"name": "<tên attribute nguyên văn>", "gloss": "<câu ngắn tích cực>", \
"synonyms": "<các cách gõ, ngăn cách bằng dấu phẩy>", "queries": ["<truy vấn 1>", "<truy vấn 2>"], \
"englishName": "<nhãn tiếng Anh ngắn, lowercase, hyphenated>"}]}

Ví dụ input:
Attributes cần viết mô tả:
- "check-in" (áp dụng cho: Homestay, Điểm tham quan)
  Cần phân biệt rõ với: "view đẹp", "du lịch"
  Mô tả POI thật có attribute này:
    • Địa điểm check-in nổi tiếng ở Đà Lạt, gần hồ Xuân Hương.
    • Homestay có sân vườn, phù hợp nhóm bạn và chụp ảnh.

Ví dụ output (LƯU Ý: không nhắc "view đẹp"/"du lịch", không phủ định, không nói tới nhận phòng \
khách sạn):
{"items": [{"name": "check-in", "gloss": "địa điểm khung cảnh đẹp độc đáo để chụp ảnh sống ảo \
đăng mạng xã hội", "synonyms": "chỗ chụp ảnh đẹp, sống ảo, điểm sống ảo, chụp hình, photo spot, \
góc sống ảo", "queries": ["địa điểm check-in đẹp ở Đà Lạt", "chỗ chụp ảnh sống ảo gần đây", \
"điểm sống ảo view đẹp"], "englishName": "check-in"}]}
"""

_JSON_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AttributeContext:
    """Grounding + contrastive context for one attribute, prepared for the LLM."""

    __slots__ = ("attribute", "categories", "descriptions", "contrast_names", "cluster_label")

    def __init__(
        self,
        attribute: Attribute,
        categories: list[str],
        descriptions: list[str],
        contrast_names: list[str],
        cluster_label: int,
    ) -> None:
        self.attribute = attribute
        self.categories = categories
        self.descriptions = descriptions
        self.contrast_names = contrast_names
        self.cluster_label = cluster_label


async def _fetch_attributes(db: Prisma, only_null: bool, limit: int | None) -> list[Attribute]:
    """Load attributes to process, optionally limited to missing descriptions."""
    where = {"description": None} if only_null else {}
    attributes = await db.attribute.find_many(where=where, order={"attributeName": "asc"})
    return attributes[:limit] if limit else attributes


async def _fetch_all_attributes(db: Prisma) -> list[Attribute]:
    """Load every attribute row, for clustering/contrast grounding."""
    return await db.attribute.find_many(order={"attributeName": "asc"})


async def _fetch_sample_categories(db: Prisma, attribute_id: str, limit: int) -> list[str]:
    """Fetch distinct POI categories linked to this attribute, for grounding.

    Categories are less noisy than brand/POI names — they signal *where* an
    attribute applies without dragging brand identity into the description.
    """
    links = await db.poiattribute.find_many(
        where={"attributeId": attribute_id},
        include={"poi": {"include": {"brand": True}}},
        take=limit * 5,
    )
    categories: list[str] = []
    for link in links:
        poi = link.poi
        category = poi.brand.category if poi and poi.brand and poi.brand.category else None
        if category and category not in categories:
            categories.append(category)
        if len(categories) >= limit:
            break
    return categories


async def _fetch_sample_descriptions(db: Prisma, attribute_id: str, limit: int) -> list[str]:
    """Fetch real, full-length POI descriptions of POIs linked to this attribute.

    This is the primary grounding signal: it lets the LLM write from evidence
    of what the attribute actually means in this dataset, rather than guessing
    from the bare name (see the "check-in" ambiguity this fixes). Descriptions
    are deduplicated but never truncated — they are already short sentences,
    and downstream batching (by cluster) keeps prompt size in check.
    """
    links = await db.poiattribute.find_many(
        where={"attributeId": attribute_id},
        include={"poi": True},
        take=limit * 5,
    )
    descriptions: list[str] = []
    for link in links:
        poi = link.poi
        description = poi.description.strip() if poi and poi.description else None
        if description and description not in descriptions:
            descriptions.append(description)
        if len(descriptions) >= limit:
            break
    return descriptions


def _embed_attribute_names(embedding_client: EmbeddingServiceClient, names: list[str]) -> np.ndarray:
    """Embed attribute names (bge-m3 dense vectors) for clustering/k-NN.

    Clustering on the bare name (not on POI-description centroids) is the
    empirically better signal here: real POI descriptions are multi-attribute,
    so their per-attribute centroids collapse into one generic blob. The name
    space keeps genuine synonyms close (wifi/wifi mạnh, giá rẻ/giá hợp lý)
    while a tight threshold (~0.25) keeps merely-adjacent names apart
    (đi bộ/đi dạo vs gần X).
    """
    embeddings = embedding_client.embed_hybrid_documents(names, model=settings.EMBEDDING_SERVICE_MODEL)
    return np.array([item["dense_vector"] for item in embeddings])


def _cluster_attribute_names(vectors: np.ndarray, distance_threshold: float) -> np.ndarray:
    """Cluster attribute name embeddings into near-synonym groups.

    Uses Agglomerative clustering with cosine distance and no fixed ``k`` —
    the taxonomy is a mix of a few near-synonym clusters (price, romance,
    family, check-in/view/travel...) and many unrelated singletons, so a
    method that lets cluster count emerge from a distance threshold (average
    linkage, to avoid single-linkage chaining) fits better than k-means/DBSCAN
    on only ~80 points.
    """
    n = len(vectors)
    if n < 2:
        return np.zeros(n, dtype=int)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    return clustering.fit_predict(vectors)


def _nearest_neighbors(vectors: np.ndarray, k: int) -> list[list[int]]:
    """Return, for each row, the indices of its top-k cosine-nearest others."""
    n = len(vectors)
    if n < 2:
        return [[] for _ in range(n)]
    similarity = cosine_similarity(vectors)
    np.fill_diagonal(similarity, -np.inf)
    k = min(k, n - 1)
    neighbor_indices = np.argsort(-similarity, axis=1)[:, :k]
    return neighbor_indices.tolist()


def _build_contrast_names(
    index: int,
    names: list[str],
    labels: np.ndarray,
    neighbor_indices: list[list[int]],
) -> list[str]:
    """Union cluster-mates (same label) and k-NN hard negatives, self excluded."""
    contrast: list[str] = []
    label = labels[index]
    for other_index, other_label in enumerate(labels):
        if other_index != index and other_label == label:
            contrast.append(names[other_index])
    for other_index in neighbor_indices[index]:
        name = names[other_index]
        if name not in contrast:
            contrast.append(name)
    return contrast[:MAX_CONTRAST_NAMES]


def _pack_batches_by_cluster(contexts: list[AttributeContext], batch_size: int) -> list[list[AttributeContext]]:
    """Pack attributes into LLM-call batches, never splitting a cluster.

    Groups are packed greedily in encounter order, filling each batch up to
    ``batch_size``. A cluster larger than ``batch_size`` still goes out whole,
    as its own (oversized) batch, so contrastive grouping is never broken.
    """
    groups: dict[int, list[AttributeContext]] = {}
    order: list[int] = []
    for context in contexts:
        label = context.cluster_label
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(context)

    batches: list[list[AttributeContext]] = []
    current: list[AttributeContext] = []
    for label in order:
        group = groups[label]
        if current and len(current) + len(group) > batch_size:
            batches.append(current)
            current = []
        if len(group) > batch_size:
            logger.warning(
                "Cluster %s has %s attributes, exceeding batch_size=%s — kept whole in one call",
                label,
                len(group),
                batch_size,
            )
        current.extend(group)
        if len(current) >= batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches


def _format_attribute_block(context: AttributeContext) -> str:
    lines = [f'- "{context.attribute.attributeName}"']
    if context.categories:
        lines[0] += f' (áp dụng cho: {", ".join(context.categories)})'
    if context.contrast_names:
        quoted = ", ".join(f'"{name}"' for name in context.contrast_names)
        lines.append(f"  Cần phân biệt rõ với: {quoted}")
    if context.descriptions:
        lines.append("  Mô tả POI thật có attribute này:")
        for description in context.descriptions:
            lines.append(f"    • {description}")
    return "\n".join(lines)


def _parse_llm_json(content: str) -> list[dict[str, str]]:
    cleaned = _JSON_FENCE_PATTERN.sub("", content.strip())
    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        parsed = parsed.get("items")
    if not isinstance(parsed, list):
        raise ValueError("LLM response is not a JSON array under 'items'")
    return parsed


def _normalize_queries(raw_queries: object) -> list[str]:
    """Coerce the LLM's ``queries`` field into a clean list of strings."""
    if isinstance(raw_queries, str):
        raw_queries = [raw_queries]
    if not isinstance(raw_queries, list):
        return []
    queries: list[str] = []
    for item in raw_queries:
        text = str(item).strip().rstrip(".?!")
        if text and text not in queries:
            queries.append(text)
    return queries


def _build_description(gloss: str, synonyms: str, queries: list[str]) -> str:
    """Assemble the embedded text: positive gloss + how-users-type + sample queries.

    Kept deliberately lean (see the "quá dài" feedback) and POSITIVE-ONLY — no
    negation and no sibling keywords, since the whole string is embedded and a
    vector model would otherwise let those foreign tokens mis-attract queries.
    The attribute name is prepended later by ``ingest_attribute_vectors``, so it
    is not repeated here.
    """
    parts: list[str] = []
    gloss = gloss.strip().rstrip(".")
    if gloss:
        parts.append(gloss)
    synonyms = synonyms.strip().rstrip(".")
    if synonyms:
        parts.append(f"Cách gõ: {synonyms}")
    if queries:
        parts.append(f"Ví dụ: {'; '.join(queries)}")
    return ". ".join(parts)


async def _generate_batch(llm: LLM, batch: list[AttributeContext]) -> dict[str, dict[str, object]]:
    """Call the LLM once for a batch; returns name -> {gloss, synonyms, queries, combined}."""
    attribute_blocks = "\n".join(_format_attribute_block(context) for context in batch)
    user_message = f"Attributes cần viết mô tả:\n{attribute_blocks}"
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

    result: dict[str, dict[str, object]] = {}
    for item in items:
        name = str(item.get("name", "")).strip()
        gloss = str(item.get("gloss", "")).strip()
        synonyms = str(item.get("synonyms", "")).strip()
        queries = _normalize_queries(item.get("queries"))
        english_name = str(item.get("englishName", "")).strip()
        combined = _build_description(gloss, synonyms, queries)
        if name and combined:
            result[name] = {
                "gloss": gloss,
                "synonyms": synonyms,
                "queries": queries,
                "combined": combined,
                "englishName": english_name,
            }
    return result


async def _update_signal_vietnam_names(db: Prisma) -> None:
    """Upsert ``vietnamName`` cho các ranking signal từ ``SIGNAL_VIETNAM_NAMES``."""
    for name, vi_name in SIGNAL_VIETNAM_NAMES.items():
        await db.signal.upsert(
            where={"signalName": name},
            data={
                "create": {"signalName": name, "vietnamName": vi_name},
                "update": {"vietnamName": vi_name},
            },
        )
    logger.info("Updated vietnamName for %s signals", len(SIGNAL_VIETNAM_NAMES))


async def generate_attribute_descriptions(
    only_null: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    samples_per_attr: int = DEFAULT_SAMPLES_PER_ATTR,
    cluster_distance_threshold: float = DEFAULT_CLUSTER_DISTANCE_THRESHOLD,
    knn_neighbors: int = DEFAULT_KNN_NEIGHBORS,
    output_xlsx: str | None = None,
) -> int:
    """Generate LLM-written descriptions for POI attributes.

    Args:
        only_null: Only process attributes whose description is currently null.
        batch_size: Max attributes packed into one LLM call (clusters are
            never split across calls, so an oversized cluster may exceed this).
        limit: Cap the number of attributes processed (useful for a dry run).
        samples_per_attr: Max real POI categories/descriptions shown per attribute.
        cluster_distance_threshold: Cosine-distance threshold for Agglomerative
            clustering of attribute names (lower = fewer, tighter clusters).
        knn_neighbors: Extra hard-negative neighbors added per attribute,
            beyond its cluster-mates.
        output_xlsx: If set, write generated descriptions to this .xlsx file for
            review instead of persisting them to Postgres — no ``attribute.update``
            call is made in this mode.

    Returns:
        Number of attributes generated (persisted to Postgres, or written to
        ``output_xlsx`` when set).
    """
    db = Prisma()
    llm = LLM()
    embedding_client = EmbeddingServiceClient(
        service_url=settings.EMBEDDING_SERVICE_URL,
        timeout=settings.EMBEDDING_SERVICE_TIMEOUT,
    )
    updated_count = 0

    await db.connect()
    try:
        await _update_signal_vietnam_names(db)

        attributes = await _fetch_attributes(db, only_null, limit)
        if not attributes:
            logger.warning("No attribute to process — nothing to generate")
            return 0

        all_attributes = await _fetch_all_attributes(db)
        all_names = [attr.attributeName for attr in all_attributes]
        name_to_index = {name: i for i, name in enumerate(all_names)}

        vectors = await asyncio.to_thread(_embed_attribute_names, embedding_client, all_names)
        labels = _cluster_attribute_names(vectors, cluster_distance_threshold)
        neighbor_indices = _nearest_neighbors(vectors, knn_neighbors)

        cluster_sizes: dict[int, int] = {}
        for label in labels:
            cluster_sizes[label] = cluster_sizes.get(label, 0) + 1
        for label, members in sorted(cluster_sizes.items()):
            if members > 1:
                member_names = [all_names[i] for i, lbl in enumerate(labels) if lbl == label]
                logger.info("Cluster %s (%s members): %s", label, members, member_names)

        logger.info(
            "Generating descriptions for %s attributes (only_null=%s, batch_size=%s)",
            len(attributes),
            only_null,
            batch_size,
        )

        contexts: list[AttributeContext] = []
        for attr in attributes:
            index = name_to_index[attr.attributeName]
            categories = await _fetch_sample_categories(db, attr.id, samples_per_attr)
            descriptions = await _fetch_sample_descriptions(db, attr.id, samples_per_attr)
            contrast_names = _build_contrast_names(index, all_names, labels, neighbor_indices)
            contexts.append(
                AttributeContext(
                    attribute=attr,
                    categories=categories,
                    descriptions=descriptions,
                    contrast_names=contrast_names,
                    cluster_label=int(labels[index]),
                )
            )

        batches = _pack_batches_by_cluster(contexts, batch_size)
        records: list[dict[str, object]] = []

        for batch_index, batch in enumerate(batches):
            names_in_batch = [context.attribute.attributeName for context in batch]
            try:
                descriptions = await _generate_batch(llm, batch)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                logger.error(
                    "Batch %s/%s (%s) failed (%s) — retrying once",
                    batch_index + 1,
                    len(batches),
                    names_in_batch,
                    exc,
                )
                try:
                    descriptions = await _generate_batch(llm, batch)
                except (LLMError, ValueError, json.JSONDecodeError) as retry_exc:
                    logger.error(
                        "Batch %s/%s (%s) failed again, skipping (%s)",
                        batch_index + 1,
                        len(batches),
                        names_in_batch,
                        retry_exc,
                    )
                    continue

            for context in batch:
                entry = descriptions.get(context.attribute.attributeName)
                if not entry:
                    logger.warning("No description returned for %r", context.attribute.attributeName)
                    continue
                # Chỉ dùng englishName do LLM sinh khi attribute chưa có sẵn (không ghi đè
                # giá trị đã curated từ ATTRIBUTE_ENGLISH_NAMES trong ingest_poi_data.py).
                english_name = context.attribute.englishName or entry["englishName"]
                if output_xlsx:
                    records.append(
                        {
                            "attribute_id": context.attribute.id,
                            "attribute_name": context.attribute.attributeName,
                            "cluster_label": context.cluster_label,
                            "contrast_names": "; ".join(context.contrast_names),
                            "categories": "; ".join(context.categories),
                            "sample_poi_descriptions": " | ".join(context.descriptions),
                            "gloss": entry["gloss"],
                            "synonyms": entry["synonyms"],
                            "queries": "; ".join(entry["queries"]),
                            "final_description": entry["combined"],
                            "english_name": english_name,
                        }
                    )
                else:
                    update_data: dict[str, Any] = {"description": entry["combined"]}
                    if entry["englishName"] and not context.attribute.englishName:
                        update_data["englishName"] = entry["englishName"]
                    await db.attribute.update(
                        where={"id": context.attribute.id},
                        data=update_data,
                    )
                updated_count += 1

            logger.info("Progress: %s/%s attributes generated", updated_count, len(contexts))

        if output_xlsx:
            pd.DataFrame(records).to_excel(output_xlsx, index=False)
            logger.info("Wrote %s attribute description(s) to %s", updated_count, output_xlsx)
        else:
            logger.info("Done: %s/%s attributes updated", updated_count, len(contexts))
        return updated_count
    finally:
        await db.disconnect()
        embedding_client.close()


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
    parser.add_argument(
        "--samples-per-attr",
        type=int,
        default=DEFAULT_SAMPLES_PER_ATTR,
        help="Max real POI categories/descriptions shown per attribute for grounding.",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=float,
        default=DEFAULT_CLUSTER_DISTANCE_THRESHOLD,
        help="Cosine-distance threshold for clustering attribute names (lower = tighter clusters).",
    )
    parser.add_argument(
        "--knn-neighbors",
        type=int,
        default=DEFAULT_KNN_NEIGHBORS,
        help="Extra hard-negative neighbors added per attribute, beyond its cluster-mates.",
    )
    parser.add_argument(
        "--output-xlsx",
        type=str,
        default=None,
        help=(
            "Write generated descriptions to this .xlsx file for review instead of "
            "persisting them to Postgres (no attribute.update is called)."
        ),
    )
    args = parser.parse_args()

    count = asyncio.run(
        generate_attribute_descriptions(
            only_null=args.only_null,
            batch_size=args.batch_size,
            limit=args.limit,
            samples_per_attr=args.samples_per_attr,
            cluster_distance_threshold=args.cluster_threshold,
            knn_neighbors=args.knn_neighbors,
            output_xlsx=args.output_xlsx,
        )
    )
    if args.output_xlsx:
        print(f"Wrote {count} attribute description(s) to {args.output_xlsx}")
    else:
        print(f"Updated {count} attribute description(s)")


if __name__ == "__main__":
    main()
