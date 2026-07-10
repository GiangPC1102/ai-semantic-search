# AICore

Backend AI service (FastAPI + LiteLLM + Qdrant + Postgres) và pipeline offline nạp dữ liệu POI.

## Yêu cầu

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) để quản lý dependency
- Docker + Docker Compose (để chạy Postgres, Qdrant, embedding service)

## 1. Cài dependency

```bash
cd AICore
uv sync
```

## 2. Chuẩn bị `.env`

Tạo/điền file `AICore/.env` với các biến sau (đã có sẵn giá trị mặc định cho local):

```dotenv
# Vector DB
QDRANT_URL=http://qdrant:6333
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_POI_COLLECTION=tasco_poi

# Embedding service
EMBEDDING_SERVICE_URL=embedding:50051
EMBEDDING_SERVICE_MODEL=bge-m3

# LLM Gateway (LiteLLM) — dùng chung cho API service và pipeline offline
OPENAI_API_KEY=<điền API key OpenAI thật của bạn>
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.7

# Postgres (pipeline offline)
DATABASE_URL=postgresql+psycopg://aicore:aicore@localhost:5432/aicore

# Nguồn dữ liệu POI
POI_DATASET_PATH=data/raw/ai_maps_track2_dataset_participants.xlsx
POI_DATASET_SHEET=POI_Dataset

# Điều khiển LLM trong pipeline (Phase 2/3)
LLM_TAXONOMY_ENABLED=true
LLM_BATCH_SIZE=20
```

`OPENAI_API_KEY` là secret — không commit giá trị thật vào git.

## 3. Khởi động Postgres

```bash
# từ thư mục gốc repo (nơi có docker-compose.yml)
docker compose up -d postgres
```

Postgres chạy tại `localhost:5432`, user/password/db đều là `aicore` (khớp `DATABASE_URL` mặc định ở trên).

## 4. Migrate schema (Alembic)

```bash
cd AICore
uv run alembic upgrade head
```

Lệnh này tạo các bảng core (`pois`, `poi_signals`, `taxonomy_aliases`, `search_documents`, ...) theo `migrations/versions/`.

## 5. Chạy pipeline offline nạp dữ liệu POI

Pipeline gồm 4 phase, chạy tuần tự theo đúng thứ tự (mỗi phase phụ thuộc output của phase trước):

```bash
cd AICore

# Phase 1 — đọc file Excel, chuẩn hóa, upsert POI vào Postgres
uv run python -m app.tasco_data --phase 1

# Phase 2 — chuẩn hóa taxonomy động bằng LLM (bỏ qua nếu LLM_TAXONOMY_ENABLED=false
# hoặc thiếu OPENAI_API_KEY)
uv run python -m app.tasco_data --phase 2

# Phase 3 — sinh signal xác định (deterministic) + enrich bằng LLM
uv run python -m app.tasco_data --phase 3

# Phase 4 — build search_documents (semantic + keyword text) phục vụ tìm kiếm/embedding
uv run python -m app.tasco_data --phase 4
```

Có thể chỉ định file dataset/sheet khác thay vì lấy từ `.env`:

```bash
uv run python -m app.tasco_data data/raw/other_dataset.xlsx --sheet Sheet1 --phase 1
```

Phase 1 và Phase 4 idempotent (chạy lại nhiều lần không tạo trùng dữ liệu). Phase 2/3 gọi LLM thật qua LiteLLM — cần `OPENAI_API_KEY` hợp lệ, nếu không sẽ log warning và bỏ qua phần enrichment bằng LLM (vẫn giữ lại phần signal xác định ở Phase 3).

## 6. Chạy API service

```bash
docker compose up -d --build aicore-api
```

hoặc dùng `make dev` ở thư mục gốc repo để dựng toàn bộ stack (Postgres, Qdrant, embedding, aicore-api).
