"""Setup toàn bộ database cho dự án bằng MỘT lệnh duy nhất.

Dành cho dev mới clone repo: tạo bảng Postgres, ingest POI dataset, sinh mô tả
attribute bằng LLM, rồi nạp vector vào Qdrant — theo đúng thứ tự phụ thuộc.

    uv run python -m app.scripts.setup_database

Thứ tự thực hiện (dừng ngay nếu bước nào lỗi, có thể chạy lại an toàn vì mọi
bước đều idempotent — upsert theo unique key):
    1. `prisma generate` + `prisma migrate deploy` — tạo/migrate schema Postgres.
    2. `ingest_poi_data` (phase 2-4) — seed signals, brands, poi, attributes
       (suy ra từ trường `attributes` trong POI_DATASET), poi_attributes, poi_tags.
    3. `generate_attribute_descriptions` — sinh mô tả tiếng Việt cho attribute qua LLM.
    4. `ingest_attribute_vectors` + `ingest_poi_vectors` — embed (bge-m3) và upsert
       vào 2 collection Qdrant, ghi lại `vectorId` tương ứng vào Postgres.

Yêu cầu trước khi chạy: hạ tầng (Postgres, Qdrant, embedding service) đã chạy
(`make dev` từ thư mục gốc repo) và `AICore/.env` đã cấu hình đủ biến (xem README.md).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

from app.core.logger import logger
from app.scripts.generate_attribute_descriptions import generate_attribute_descriptions
from app.scripts.ingest_attribute_vectors import ingest_attribute_vectors
from app.scripts.ingest_poi_data import run_ingest
from app.scripts.ingest_poi_vectors import ingest_poi_vectors


PRISMA_SCHEMA_PATH = "app/prisma/schema.prisma"


def _run_prisma(*args: str) -> None:
    command = [sys.executable, "-m", "prisma", *args, f"--schema={PRISMA_SCHEMA_PATH}"]
    logger.info("$ %s", " ".join(command))
    subprocess.run(command, check=True)


async def setup_database(skip_migrate: bool = False, recreate_vectors: bool = False) -> None:
    if skip_migrate:
        logger.info("Bỏ qua prisma generate/migrate (--skip-migrate)")
    else:
        logger.info("=== Step 1/4: prisma generate + migrate deploy ===")
        _run_prisma("generate")
        _run_prisma("migrate", "deploy")

    logger.info("=== Step 2/4: ingest POI dataset (signals, brands, poi, attributes, tags) ===")
    await run_ingest("all")

    logger.info("=== Step 3/4: generate attribute descriptions (LLM) ===")
    await generate_attribute_descriptions()

    logger.info("=== Step 4/4: ingest vectors vào Qdrant (attribute_data + poi_data) ===")
    await ingest_attribute_vectors(recreate=recreate_vectors)
    await ingest_poi_vectors(recreate=recreate_vectors)

    logger.info("Setup database hoàn tất.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Bỏ qua `prisma generate`/`prisma migrate deploy` (đã chạy trước đó).",
    )
    parser.add_argument(
        "--recreate-vectors",
        action="store_true",
        help="Xoá và tạo lại 2 Qdrant collection trước khi ingest vector.",
    )
    args = parser.parse_args()

    asyncio.run(setup_database(skip_migrate=args.skip_migrate, recreate_vectors=args.recreate_vectors))


if __name__ == "__main__":
    main()
