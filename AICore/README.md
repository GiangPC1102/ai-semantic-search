# AICore — Data Pipeline

Hướng dẫn chạy các script để dựng schema PostgreSQL, đọc dữ liệu từ file Excel,
ingest vào từng bảng, sinh mô tả (description) cho attribute bằng LLM, và nạp
vector vào Qdrant để phục vụ semantic search.

## 1. Yêu cầu trước khi chạy

- Python >= 3.12, [uv](https://docs.astral.sh/uv/) để quản lý virtualenv/dependencies.
- Docker + Docker Compose (chạy PostgreSQL, Qdrant, embedding service).
- File dataset Excel đặt tại `data/ai_maps_track2_dataset_participants.xlsx`
  (đường dẫn mặc định, có thể override bằng `--file`).
- Đã cấu hình `AICore/.env` (xem `AICore/app/core/config.py`), tối thiểu:
  - `DATABASE_URL` — kết nối PostgreSQL.
  - `QDRANT_URL` / `QDRANT_HOST` / `QDRANT_PORT` — kết nối Qdrant.
  - `EMBEDDING_SERVICE_URL` — gRPC endpoint của embedding service (bge-m3).
  - `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` — dùng để sinh attribute description.

Khởi động hạ tầng (Postgres, Qdrant, embedding service, aicore-api) từ thư mục gốc repo:

```bash
make dev
# tương đương: docker compose up -d --build
```

Cài dependency Python (chạy trong `AICore/`):

```bash
cd AICore
uv sync
```

Tất cả lệnh bên dưới chạy từ thư mục `AICore/` bằng `uv run` (hoặc kích hoạt
`.venv` rồi bỏ tiền tố `uv run`).

## 2. Tạo bảng (Prisma migrate)

Tạo schema PostgreSQL (`brands`, `poi`, `attributes`, `signals`, `tags`,
`poi_attributes`, `poi_tags`) theo `app/prisma/schema.prisma`:

```bash
uv run prisma generate
uv run prisma migrate deploy
```

Dùng `prisma migrate dev --name <tên>` nếu bạn đang sửa schema và cần tạo migration mới.

## 3. Đọc file Excel và ingest dữ liệu vào từng bảng

Script `app/scripts/ingest_poi_data.py` đọc 2 sheet của file Excel
(`POI_Dataset`, `Attribute_Taxonomy`) và nạp dữ liệu theo 3 phase độc lập,
idempotent (chạy lại không tạo trùng dữ liệu):

| Phase | Nội dung                                                                             |
| ----- | ------------------------------------------------------------------------------------ |
| 2     | Seed `signals` (11 loại ranking signal) + attribute taxonomy gốc (bảng `attributes`) |
| 3     | Ingest `brands` + `poi` (bảng POI core)                                              |
| 4     | Ingest quan hệ `poi_attributes` + `poi_tags`                                         |

Chạy toàn bộ:

```bash
uv run python -m app.scripts.ingest_poi_data
```

Chạy từng phase riêng, hoặc trỏ tới file/sheet khác:

```bash
uv run python -m app.scripts.ingest_poi_data --phase 2
uv run python -m app.scripts.ingest_poi_data --phase 3
uv run python -m app.scripts.ingest_poi_data --phase 4
uv run python -m app.scripts.ingest_poi_data \
  --file data/ai_maps_track2_dataset_participants.xlsx \
  --poi-sheet POI_Dataset \
  --attribute-sheet Attribute_Taxonomy
```

## 4. Sinh mô tả (description) cho attribute bằng LLM

Bảng `attributes` sau bước 3 có thể có `description` rỗng đối với các attribute
mới phát sinh ở Phase 4 (không nằm trong sheet `Attribute_Taxonomy`). Script
`app/scripts/generate_attribute_descriptions.py` gọi LLM (OpenAI qua LiteLLM)
để sinh mô tả tiếng Việt cho từng `attribute_name`, dùng làm nội dung embedding
ở bước 5 — attribute thiếu mô tả sẽ không tìm được qua semantic search.

```bash
# Sinh lại mô tả cho toàn bộ attribute (đảm bảo văn phong nhất quán)
uv run python -m app.scripts.generate_attribute_descriptions

# Chỉ sinh cho attribute chưa có mô tả
uv run python -m app.scripts.generate_attribute_descriptions --only-null

# Giới hạn số lượng / batch size khi cần chạy thử
uv run python -m app.scripts.generate_attribute_descriptions --limit 20 --batch-size 10
```

## 5. Ingest dữ liệu vào Qdrant

Hai collection Qdrant riêng biệt: `poi_data` (mô tả POI) và `attribute_data`
(mô tả attribute). Cả hai script bên dưới tự động embed text qua embedding
service (bge-m3) và upsert vào Qdrant, đồng thời ghi lại `vector_id` tương ứng
vào PostgreSQL.

Ingest attribute (yêu cầu đã có `description` từ bước 4):

```bash
uv run python -m app.scripts.ingest_attribute_vectors
# thêm --recreate để xoá và tạo lại collection từ đầu
uv run python -m app.scripts.ingest_attribute_vectors --recreate
```

Ingest POI (yêu cầu POI có `description` — cột `description` trong sheet `POI_Dataset`):

```bash
uv run python -m app.scripts.ingest_poi_vectors
uv run python -m app.scripts.ingest_poi_vectors --recreate
```

## 6. Thứ tự chạy đầy đủ (từ đầu)

```bash
cd AICore
uv sync
uv run prisma generate
uv run prisma migrate deploy

uv run python -m app.scripts.ingest_poi_data
uv run python -m app.scripts.generate_attribute_descriptions
uv run python -m app.scripts.ingest_attribute_vectors
uv run python -m app.scripts.ingest_poi_vectors
```

## 7. (Tuỳ chọn) Đánh giá kết quả search

Sau khi API `aicore-api` đang chạy (`make dev` hoặc `make build-aicore-api`),
đánh giá recall của `/tasco/search` trên sheet `Public_Evaluation`:

```bash
uv run python -m app.scripts.evaluate_tasco_search
```

Kết quả được ghi ra `data/tasco_search_evaluation.xlsx`.
