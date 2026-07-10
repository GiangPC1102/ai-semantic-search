# Offline Pipeline Coding Plan — Python + PostgreSQL + Qdrant + BGE-M3 + LiteLLM

## 0. Mục tiêu

Tài liệu này là bản cập nhật cho Offline Pipeline của dự án Python.

Pipeline tổng thể:

```text
POI Dataset
→ Schema normalization
→ Text normalization
→ Taxonomy lookup
→ Unknown value detection
→ LiteLLM taxonomy normalization for unknown values
→ Opening hours parser + LiteLLM fallback if needed
→ Generate poi_signals
→ LLM-assisted signal & intent enrichment
→ Generate semantic_text / keyword_text
→ Generate poi_search_documents
→ Generate BGE-M3 embeddings
→ Save vectors to Qdrant
```

---

# 1. Core Postgres tables

Chỉ dùng 4 bảng core:

```text
1. pois
2. poi_signals
3. taxonomy_aliases
4. poi_search_documents
```

Raw dataset gốc chỉ lưu ở:

```text
data/raw/
```

---

# 2. Vai trò từng bảng

## 2.1. `pois`

Lưu source of truth của POI.

Dùng cho:

```text
- Hard filter category.
- Hard filter city / district.
- Opening-hours filter.
- Price filter.
- Tie-break ranking bằng rating, review_count, popularity_score.
- Fetch full POI để trả kết quả.
```

## 2.2. `poi_signals`

Unified signal/evidence layer.

Vì attribute, tag, intent, time, price, quality đều là signal.

Dùng cho:

```text
- filter mềm/cứng
- rerank
- explanation
- evidence builder
```

## 2.3. `taxonomy_aliases`

Không phải hard-code cố định.

Bảng này là:

```text
- normalization cache
- taxonomy memory
- query parser dictionary
- nơi lưu kết quả LLM normalization để tái sử dụng
```

Ví dụ:

```text
"coffee shop" → cafe
"quán cafe" → cafe
"chỗ đậu xe" → parking
"yên tĩnh" → quiet
"hẹn hò" → date_night
"q1" → quan_1
```

Nếu pipeline gặp giá trị mới chưa có trong bảng này:

```text
1. collect unknown values
2. call LiteLLM
3. nhận normalized mapping
4. validate
5. insert vào taxonomy_aliases
6. dùng mapping đó cho POI hiện tại và các lần sau
```

## 2.4. `poi_search_documents`

Lưu nội dung được embedding.

```text
pois + poi_signals
→ build content
→ BGE-M3 embedding
→ Qdrant point
```

---

# 3. Python stack

```text
Language: Python 3.11+
ORM: SQLAlchemy 2.x
Migration: Alembic
DB driver: psycopg
Database: PostgreSQL
Vector DB: Qdrant
Embedding: BGE-M3 / FlagEmbedding
LLM Client: LiteLLM
Default LLM provider: OpenAI
Default LLM model: openai/gpt-4o
Excel reader: pandas + openpyxl
Validation: pydantic
```

---

# 4. Python packages

```bash
pip install sqlalchemy alembic psycopg[binary]
pip install pandas openpyxl
pip install pydantic pydantic-settings
pip install qdrant-client
pip install FlagEmbedding
pip install litellm
pip install python-dotenv
pip install tqdm
```

---

# 5. Environment variables

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/tasco_maps

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=poi_search

EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_MODE=local

# LiteLLM defaults
LLM_PROVIDER=openai
LLM_MODEL=openai/gpt-4o
OPENAI_API_KEY=your_openai_api_key

# LLM control
LLM_TAXONOMY_ENABLED=true
LLM_SIGNAL_ENRICHMENT_ENABLED=true
LLM_OPENING_HOURS_FALLBACK_ENABLED=true
LLM_BATCH_SIZE=20
LLM_TEMPERATURE=0
```

---

# 6. PostgreSQL extensions

Alembic migration đầu tiên:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

PostGIS có thể thêm sau nếu cần distance search nâng cao.

---

# 7. SQLAlchemy models

File gợi ý:

```text
app/db/models.py
```

## 7.1. Base setup

```python
from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass
```

---

## 7.2. Model `Poi`

```python
class Poi(Base):
    __tablename__ = "pois"

    poi_id: Mapped[str] = mapped_column(String, primary_key=True)

    poi_name: Mapped[str] = mapped_column(Text, nullable=False)
    poi_name_norm: Mapped[Optional[str]] = mapped_column(Text)
    brand: Mapped[Optional[str]] = mapped_column(Text)
    brand_norm: Mapped[Optional[str]] = mapped_column(Text)

    category: Mapped[Optional[str]] = mapped_column(Text)
    category_norm: Mapped[Optional[str]] = mapped_column(Text)
    sub_category: Mapped[Optional[str]] = mapped_column(Text)
    sub_category_norm: Mapped[Optional[str]] = mapped_column(Text)

    city: Mapped[Optional[str]] = mapped_column(Text)
    city_norm: Mapped[Optional[str]] = mapped_column(Text)
    district: Mapped[Optional[str]] = mapped_column(Text)
    district_norm: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    address_norm: Mapped[Optional[str]] = mapped_column(Text)

    latitude: Mapped[Optional[float]] = mapped_column()
    longitude: Mapped[Optional[float]] = mapped_column()

    rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    review_count: Mapped[Optional[int]] = mapped_column(Integer)
    popularity_score: Mapped[Optional[int]] = mapped_column(Integer)
    price_level: Mapped[Optional[int]] = mapped_column(Integer)

    opening_hours_raw: Mapped[Optional[str]] = mapped_column(Text)
    open_time: Mapped[Optional[time]] = mapped_column(Time)
    close_time: Mapped[Optional[time]] = mapped_column(Time)
    is_24_7: Mapped[bool] = mapped_column(Boolean, default=False)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, default=False)
    opening_hours_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    description: Mapped[Optional[str]] = mapped_column(Text)
    description_norm: Mapped[Optional[str]] = mapped_column(Text)

    semantic_text: Mapped[Optional[str]] = mapped_column(Text)
    keyword_text: Mapped[Optional[str]] = mapped_column(Text)

    enrichment_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    signals: Mapped[list["PoiSignal"]] = relationship(
        back_populates="poi",
        cascade="all, delete-orphan",
    )

    search_documents: Mapped[list["PoiSearchDocument"]] = relationship(
        back_populates="poi",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_pois_category_norm", "category_norm"),
        Index("idx_pois_city_norm", "city_norm"),
        Index("idx_pois_district_norm", "district_norm"),
        Index("idx_pois_price_level", "price_level"),
        Index("idx_pois_is_24_7", "is_24_7"),
        Index("idx_pois_open_close_time", "open_time", "close_time"),
        Index("idx_pois_rating", "rating"),
        Index("idx_pois_popularity", "popularity_score"),
    )
```

---

## 7.3. Model `PoiSignal`

```python
class PoiSignal(Base):
    __tablename__ = "poi_signals"

    signal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    poi_id: Mapped[str] = mapped_column(
        ForeignKey("pois.poi_id", ondelete="CASCADE"),
        nullable=False,
    )

    signal_type: Mapped[str] = mapped_column(String, nullable=False)
    signal_name: Mapped[str] = mapped_column(Text, nullable=False)
    signal_norm: Mapped[str] = mapped_column(Text, nullable=False)

    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_number: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    value_boolean: Mapped[Optional[bool]] = mapped_column(Boolean)

    is_filterable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rankable: Mapped[bool] = mapped_column(Boolean, default=True)

    constraint_default: Mapped[str] = mapped_column(String, default="soft")
    rank_behavior: Mapped[str] = mapped_column(String, default="boost")

    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.0"))
    source: Mapped[Optional[str]] = mapped_column(String)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    poi: Mapped["Poi"] = relationship(back_populates="signals")

    __table_args__ = (
        Index("idx_poi_signals_poi", "poi_id"),
        Index("idx_poi_signals_type_norm", "signal_type", "signal_norm"),
        Index("idx_poi_signals_norm", "signal_norm"),
        Index("idx_poi_signals_filterable", "is_filterable"),
        Index("idx_poi_signals_rankable", "is_rankable"),
        UniqueConstraint(
            "poi_id",
            "signal_type",
            "signal_norm",
            "source",
            name="uq_poi_signal_unique",
        ),
    )
```

---

## 7.4. Model `TaxonomyAlias`

```python
class TaxonomyAlias(Base):
    __tablename__ = "taxonomy_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    alias_type: Mapped[str] = mapped_column(String, nullable=False)
    alias_text: Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm: Mapped[str] = mapped_column(Text, nullable=False)

    target_id: Mapped[str] = mapped_column(String, nullable=False)
    target_norm: Mapped[str] = mapped_column(Text, nullable=False)
    target_display: Mapped[Optional[str]] = mapped_column(Text)

    constraint_default: Mapped[str] = mapped_column(String, default="soft")
    is_hard_capable: Mapped[bool] = mapped_column(Boolean, default=False)

    language: Mapped[Optional[str]] = mapped_column(String)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.0"))
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    source: Mapped[str] = mapped_column(String, default="manual_seed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_taxonomy_alias_type", "alias_type"),
        Index("idx_taxonomy_alias_norm", "alias_norm"),
        Index("idx_taxonomy_target", "target_id"),
        UniqueConstraint(
            "alias_type",
            "alias_norm",
            "target_id",
            name="uq_taxonomy_alias_unique",
        ),
    )
```

### `source` convention

```text
manual_seed
llm_taxonomy_normalization
rule_generated
user_feedback
```

---

## 7.5. Model `PoiSearchDocument`

```python
class PoiSearchDocument(Base):
    __tablename__ = "poi_search_documents"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True)
    poi_id: Mapped[str] = mapped_column(
        ForeignKey("pois.poi_id", ondelete="CASCADE"),
        nullable=False,
    )

    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_norm: Mapped[Optional[str]] = mapped_column(Text)

    embedding_model: Mapped[str] = mapped_column(String, default="BAAI/bge-m3")
    qdrant_collection: Mapped[str] = mapped_column(String, default="poi_search")
    qdrant_point_id: Mapped[Optional[str]] = mapped_column(String)

    embedding_version: Mapped[Optional[str]] = mapped_column(String)
    content_hash: Mapped[Optional[str]] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    poi: Mapped["Poi"] = relationship(back_populates="search_documents")

    __table_args__ = (
        Index("idx_poi_search_documents_poi", "poi_id"),
        Index("idx_poi_search_documents_type", "doc_type"),
        Index("idx_poi_search_documents_qdrant_point", "qdrant_point_id"),
    )
```

---

# 8. Raw SQL indexes

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE INDEX IF NOT EXISTS idx_pois_name_trgm
ON pois USING GIN (poi_name_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_pois_brand_trgm
ON pois USING GIN (brand_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_pois_address_trgm
ON pois USING GIN (address_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_pois_keyword_trgm
ON pois USING GIN (keyword_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_poi_signals_norm_trgm
ON poi_signals USING GIN (signal_norm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_taxonomy_alias_norm_trgm
ON taxonomy_aliases USING GIN (alias_norm gin_trgm_ops);
```

---

# 9. LiteLLM service

File:

```text
app/offline/services/litellm_service.py
```

## 9.1. Basic call

```python
import json
from litellm import completion


class LiteLLMService:
    def __init__(self, model: str = "openai/gpt-4o", temperature: float = 0):
        self.model = model
        self.temperature = temperature

    def complete_json(self, system_prompt: str, user_payload: dict) -> dict:
        response = completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)
```

## 9.2. Why LiteLLM

LiteLLM cho phép gọi nhiều provider bằng một interface thống nhất, theo format tương thích OpenAI. Mặc định trong project này dùng:

```text
model = openai/gpt-4o
```

---

# 10. Minimal taxonomy seed

Không seed quá nhiều.

Chỉ seed những alias chắc chắn và phổ biến:

```text
category:
- cafe / quán cà phê / coffee shop
- restaurant / nhà hàng / quán ăn
- hotel / khách sạn
- atm
- gas station / trạm xăng
- mall / trung tâm thương mại
- pharmacy / nhà thuốc

basic attribute:
- wifi
- parking / bãi đỗ xe / chỗ đậu xe
- toilet
- swimming pool / hồ bơi
- quiet / yên tĩnh
- nice view / view đẹp
- romantic / lãng mạn
- family friendly / phù hợp gia đình
- open late / mở khuya

basic intent:
- work_or_study
- date_night
- family_kids
- tourist_checkin
- late_night_food
- beach_hotel
```

Mục tiêu của seed:

```text
- đảm bảo pipeline chạy được ngay
- không hard-code toàn bộ dataset public
- unknown value sẽ được xử lý bằng LiteLLM và lưu lại
```

---

# 11. Unknown detection strategy

## 11.1. Khi nào coi là unknown?

Một value được coi là unknown nếu:

```text
- Không exact match trong taxonomy_aliases theo alias_type.
- Không fuzzy match đủ confidence.
- Không nằm trong built-in parser rule.
```

Ví dụ unknown:

```text
category: "rooftop lounge"
attribute: "pet friendly"
tag: "kid zone"
location: "thảo điền"
opening_hours: "mở từ sáng đến khuya"
```

## 11.2. Không gọi LLM từng value một

Không nên call LLM cho từng item vì tốn chi phí và chậm.

Nên batch:

```text
collect unknown values
group by alias_type
deduplicate
call LLM per batch
insert mappings into taxonomy_aliases
continue pipeline
```

Ví dụ:

```python
unknowns = {
    "category": ["rooftop lounge", "coworking cafe"],
    "attribute": ["pet friendly", "kid zone"],
    "location": ["thao dien", "my khe"],
}
```

---

# 12. LLM taxonomy normalization

## 12.1. Mục tiêu

Khi gặp value lạ, gọi LLM để quyết định:

```text
- alias_type
- target_id
- target_norm
- target_display
- constraint_default
- is_hard_capable
- metadata
```

## 12.2. System prompt

```text
You are a taxonomy normalization engine for a POI search system.

Your job:
- Normalize raw category/location/attribute/tag/intent/time expressions.
- Prefer stable, reusable normalized IDs.
- Do not overfit to a single query.
- Do not invent POI facts.
- Only normalize the provided value.
- Return strict JSON.

Rules:
- target_id must be snake_case English.
- target_norm must be normalized text without accents.
- constraint_default must be one of: hard, soft, inferred, tie_break.
- is_hard_capable should be true only for concrete facilities/constraints such as parking, toilet, swimming_pool, wifi, open_24_7.
- Ambience or subjective signals such as quiet, romantic, nice_view should not be hard-capable.
```

## 12.3. User payload

```json
{
  "alias_type": "attribute",
  "values": [
    "chỗ giữ xe",
    "pet friendly",
    "kid zone",
    "view sông"
  ],
  "existing_targets": [
    "parking",
    "wifi",
    "quiet",
    "nice_view",
    "romantic",
    "family_friendly"
  ]
}
```

## 12.4. Expected output

```json
{
  "mappings": [
    {
      "alias_text": "chỗ giữ xe",
      "alias_norm": "cho giu xe",
      "target_id": "parking",
      "target_norm": "parking",
      "target_display": "Bãi đỗ xe",
      "constraint_default": "hard",
      "is_hard_capable": true,
      "confidence": 0.95,
      "metadata": {
        "reason": "Vietnamese phrase means parking / vehicle keeping."
      }
    },
    {
      "alias_text": "pet friendly",
      "alias_norm": "pet friendly",
      "target_id": "pet_friendly",
      "target_norm": "pet friendly",
      "target_display": "Phù hợp thú cưng",
      "constraint_default": "soft",
      "is_hard_capable": false,
      "confidence": 0.9,
      "metadata": {
        "reason": "New reusable attribute."
      }
    }
  ]
}
```

## 12.5. Save mappings

Insert into `taxonomy_aliases`:

```text
source = llm_taxonomy_normalization
```

---

# 13. Opening hours parser with LLM fallback

## 13.1. Default behavior

Không gọi LLM mặc định.

Regex/rule xử lý:

```text
24/7
07:00-22:30
08:00-02:00
7:00-22:00
07h00-22h30
```

## 13.2. Khi nào call LLM?

Chỉ call LiteLLM nếu:

```text
- opening_hours_raw không parse được
- LLM_OPENING_HOURS_FALLBACK_ENABLED=true
```

Ví dụ:

```text
mở từ sáng đến khuya
thứ 2-6 mở 8h-22h, cuối tuần 9h-23h
mở cả ngày trừ chủ nhật
```

## 13.3. Prompt output

LLM output phải là JSON:

```json
{
  "type": "daily",
  "is_24_7": false,
  "open_time": "08:00",
  "close_time": "22:00",
  "crosses_midnight": false,
  "confidence": 0.82,
  "notes": "Interpreted from Vietnamese natural language."
}
```

## 13.4. Validation

Không lưu trực tiếp nếu invalid.

Validate:

```text
- open_time format HH:MM
- close_time format HH:MM
- confidence >= 0.75
```

Nếu không đủ confidence:

```text
opening_hours_json = {"type": "unknown", "raw": "..."}
open_time = null
close_time = null
```

---

# 14. LLM-assisted signal & intent enrichment

```text
Step: LLM-assisted signal & intent enrichment
```

## 14.1. Mục tiêu

Sinh thêm signals/intent từ:

```text
- POI metadata
- category/location
- attributes/tags đã normalize
- description
- opening_hours
```

Không chỉ rule-based.

## 14.2. Có còn rule không?

Có, nhưng rule chỉ là pre-signal/guardrail, không phải engine chính.

Ví dụ rule rõ ràng có thể tự tạo:

```text
is_24_7 = true → open_24_7
rating >= 4.5 → high_rating
price_level <= 2 → budget_friendly
```

Nhưng intent enrichment như:

```text
work_or_study
date_night
family_kids
tourist_checkin
beach_hotel
late_night_food
```

sẽ dùng LiteLLM để chuẩn hóa và bổ sung, sau đó validate.

## 14.3. Input cho LiteLLM

```json
{
  "poi": {
    "poi_id": "C001",
    "poi_name": "The Workshop Coffee",
    "category_norm": "cafe",
    "city_norm": "tp hcm",
    "district_norm": "quan 1",
    "opening_hours_raw": "07:00-22:30",
    "rating": 4.6,
    "price_level": 3,
    "description": "Quán cà phê specialty có không gian yên tĩnh, nhiều ổ cắm..."
  },
  "known_signals": [
    {"signal_type": "attribute", "signal_norm": "wifi"},
    {"signal_type": "attribute", "signal_norm": "quiet"},
    {"signal_type": "attribute", "signal_norm": "power_outlet"}
  ],
  "allowed_signal_types": [
    "attribute",
    "tag",
    "intent",
    "time",
    "price",
    "quality"
  ],
  "existing_taxonomy_targets": [
    "work_or_study",
    "date_night",
    "family_kids",
    "tourist_checkin",
    "beach_hotel"
  ]
}
```

## 14.4. System prompt

```text
You are an offline POI signal enrichment engine.

Your job:
- Add useful normalized signals for retrieval and ranking.
- Focus on user search intents and evidence-based signals.
- Do not invent facilities or facts not supported by source data.
- You may infer intent if there is enough evidence.
- Return strict JSON only.

Important:
- Facilities such as swimming_pool, parking, toilet, wifi must only be added if explicitly present.
- Intent signals such as work_or_study or date_night can be inferred from a combination of attributes, tags, category, and description.
- Each signal must include evidence_text.
- Each signal must include confidence.
```

## 14.5. Expected output

```json
{
  "signals": [
    {
      "signal_type": "intent",
      "signal_name": "Phù hợp làm việc/học bài",
      "signal_norm": "work_or_study",
      "is_filterable": false,
      "is_rankable": true,
      "constraint_default": "inferred",
      "rank_behavior": "boost",
      "confidence": 0.95,
      "source": "llm_signal_enrichment",
      "evidence_text": "POI có wifi, yên tĩnh và nhiều ổ cắm."
    },
    {
      "signal_type": "tag",
      "signal_name": "Laptop friendly",
      "signal_norm": "laptop_friendly",
      "is_filterable": false,
      "is_rankable": true,
      "constraint_default": "soft",
      "rank_behavior": "boost",
      "confidence": 0.9,
      "source": "llm_signal_enrichment",
      "evidence_text": "Description mentions many power outlets and quiet environment."
    }
  ],
  "semantic_summary": "Quán cà phê yên tĩnh, có wifi và ổ cắm, phù hợp làm việc hoặc học bài."
}
```

## 14.6. Validation

Reject LLM signal nếu:

```text
- Không có evidence_text.
- confidence < 0.75.
- signal_type không hợp lệ.
- facility signal không có bằng chứng explicit.
- signal_norm rỗng hoặc không snake_case.
```

Accepted signal:

```text
→ insert into poi_signals
```

Semantic summary:

```text
→ save to pois.enrichment_json
```

---

# 15. Updated Offline Pipeline steps

## Step 1 — Load POI Dataset

```text
Read Excel sheet POI_Dataset using pandas.
Return list[dict].
Do not save raw_json to DB.
Keep source file in data/raw/.
```

## Step 2 — Schema normalization

```text
Map raw columns to canonical POI fields.
Convert numeric fields.
Trim strings.
Empty string → None.
```

## Step 3 — Text normalization

```text
Generate *_norm fields.
lowercase, remove accents, clean punctuation.
```

## Step 4 — Minimal taxonomy seed

```text
Insert only stable base aliases.
Do not seed everything from public dataset.
```

## Step 5 — Taxonomy lookup and unknown collection

```text
For each category/location/attribute/tag:
- lookup taxonomy_aliases
- if found, use target_norm
- if not found, collect unknown
```

## Step 6 — LiteLLM taxonomy normalization for unknowns

```text
Batch unknown values by alias_type.
Call LiteLLM with model openai/gpt-4o.
Validate mappings.
Insert accepted mappings into taxonomy_aliases.
Re-run normalization using new aliases.
```

## Step 7 — Opening hours parser

```text
Use rule parser first.
If parser fails and fallback enabled:
- call LiteLLM opening-hours parser
- validate output
- save parsed fields if valid
```

## Step 8 — Save POIs to Postgres

```text
Upsert into pois.
No raw_json.
Keep enrichment_json empty at this point.
```

## Step 9 — Generate deterministic base signals

Generate signals that do not need LLM:

```text
category signals
location signals
explicit raw attribute signals
explicit raw tag signals
time signals from parsed opening hours
price signals from price_level
quality signals from rating/popularity/review_count
```

Save to `poi_signals`.

## Step 10 — LLM-assisted signal & intent enrichment

```text
For each POI or batch of POIs:
- send metadata + existing signals to LiteLLM
- ask for additional evidence-based signals/intents
- validate output
- save accepted signals to poi_signals
- save semantic_summary to pois.enrichment_json
```

## Step 11 — Build semantic_text and keyword_text

```text
semantic_text = POI metadata + signals + description + semantic_summary
keyword_text = normalized POI fields + signal_norms
```

Save to `pois`.

## Step 12 — Build poi_search_documents

Create:

```text
{poi_id}::full_semantic
{poi_id}::signal_intent
{poi_id}::name_location
```

Source:

```text
pois + poi_signals
```

## Step 13 — Generate BGE-M3 embeddings

```text
Embedding source = poi_search_documents.content
MVP = dense vector
Phase 2 = dense + sparse
Phase 3 = optional ColBERT/multivector
```

## Step 14 — Upsert to Qdrant

```text
Qdrant point_id = poi_search_documents.doc_id
payload.poi_id = pois.poi_id
payload.doc_id = poi_search_documents.doc_id
payload.signal_norms = signal_norm values from poi_signals
```

## Step 15 — Validate index

Check:

```text
count pois
count poi_signals
count poi_search_documents
count Qdrant points
Qdrant payload.poi_id can join back to pois
```

---

# 16. Main runner updated

```python
def run_offline_pipeline(file_path: str) -> None:
    raw_rows = load_poi_dataset(file_path)

    normalized_rows = []
    for row in raw_rows:
        item = normalize_schema(row)
        item = normalize_text_fields(item)
        normalized_rows.append(item)

    seed_minimal_taxonomy_aliases()

    alias_cache = load_taxonomy_aliases()

    normalized_rows, unknowns = normalize_with_alias_cache(
        normalized_rows,
        alias_cache,
    )

    if settings.llm_taxonomy_enabled and unknowns:
        new_aliases = normalize_unknowns_with_litellm(unknowns)
        save_taxonomy_aliases(new_aliases)

        alias_cache = load_taxonomy_aliases()
        normalized_rows, _ = normalize_with_alias_cache(
            normalized_rows,
            alias_cache,
        )

    normalized_rows = parse_opening_hours_with_optional_llm(
        normalized_rows,
    )

    save_pois(normalized_rows)

    base_signals = generate_deterministic_base_signals(normalized_rows)
    save_poi_signals(base_signals)

    if settings.llm_signal_enrichment_enabled:
        enriched_signals, enrichment_summaries = enrich_signals_with_litellm()
        save_poi_signals(enriched_signals)
        save_enrichment_summaries(enrichment_summaries)

    build_and_save_search_texts()
    build_and_save_search_documents()

    docs = get_documents_needing_embedding()
    vectors = embedding_service.encode_dense([doc.content for doc in docs])

    qdrant_service.ensure_collection(vector_size=len(vectors[0]))
    upsert_documents_to_qdrant(docs, vectors)

    validate_offline_index()
```

---

# 17. LiteLLM taxonomy normalization code sketch

```python
def normalize_unknowns_with_litellm(
    unknowns: dict[str, list[str]],
    llm: LiteLLMService,
) -> list[dict]:
    all_aliases = []

    for alias_type, values in unknowns.items():
        values = sorted(set(values))

        for batch in chunk(values, size=settings.llm_batch_size):
            payload = {
                "alias_type": alias_type,
                "values": batch,
                "existing_targets": load_existing_targets(alias_type),
            }

            result = llm.complete_json(
                system_prompt=TAXONOMY_NORMALIZATION_PROMPT,
                user_payload=payload,
            )

            mappings = validate_taxonomy_mappings(result)
            all_aliases.extend(mappings)

    return all_aliases
```

---

# 18. LiteLLM signal enrichment code sketch

```python
def enrich_poi_signals_with_litellm(
    poi: Poi,
    existing_signals: list[PoiSignal],
    llm: LiteLLMService,
) -> tuple[list[dict], dict | None]:
    payload = {
        "poi": {
            "poi_id": poi.poi_id,
            "poi_name": poi.poi_name,
            "category_norm": poi.category_norm,
            "city_norm": poi.city_norm,
            "district_norm": poi.district_norm,
            "opening_hours_raw": poi.opening_hours_raw,
            "rating": float(poi.rating) if poi.rating else None,
            "price_level": poi.price_level,
            "description": poi.description,
        },
        "known_signals": [
            {
                "signal_type": s.signal_type,
                "signal_norm": s.signal_norm,
                "evidence_text": s.evidence_text,
            }
            for s in existing_signals
        ],
    }

    result = llm.complete_json(
        system_prompt=SIGNAL_ENRICHMENT_PROMPT,
        user_payload=payload,
    )

    signals = validate_enriched_signals(result)
    summary = result.get("semantic_summary")

    return signals, {"semantic_summary": summary} if summary else None
```

---

# 19. Guardrails for LLM usage

## 19.1. Cost and latency control

```text
- LLM only runs offline.
- Batch unknown taxonomy values.
- Cache every accepted mapping in taxonomy_aliases.
- Do not call LLM again for known aliases.
- Use temperature=0.
- Add retry with exponential backoff.
```

## 19.2. Safety against hallucination

```text
- Do not accept facilities without explicit evidence.
- Do not accept low-confidence signals.
- Validate JSON schema.
- Validate signal_type and constraint_default enums.
- Validate time format for opening hours.
```

## 19.3. Repeatability

```text
- Store LLM-generated aliases in taxonomy_aliases.
- Store enrichment source = llm_signal_enrichment.
- Store evidence_text for every LLM signal.
```

---

# 20. Qdrant relation with Postgres

## Source embedding

```text
poi_search_documents.content
→ BGE-M3 embedding
→ Qdrant vector
```

## Join key

```text
Qdrant payload.poi_id = pois.poi_id
Qdrant payload.doc_id = poi_search_documents.doc_id
Qdrant point id = poi_search_documents.qdrant_point_id
```

## Qdrant payload example

```json
{
  "poi_id": "C001",
  "doc_id": "C001::full_semantic",
  "doc_type": "full_semantic",
  "category_norm": "cafe",
  "city_norm": "tp hcm",
  "district_norm": "quan 1",
  "signal_norms": ["wifi", "quiet", "work_or_study"],
  "signal_types": ["attribute", "intent"],
  "price_level": 3,
  "rating": 4.6,
  "popularity_score": 91,
  "is_24_7": false,
  "open_time": "07:00",
  "close_time": "22:30"
}
```

---

# 21. Updated implementation order

## Phase 1 — DB + ingestion — ✅ Done (2026-07-09)

```text
1. Setup SQLAlchemy + Alembic.                 [x]
2. Create 4 core tables.                       [x]
3. Add pg_trgm/unaccent indexes.                [x]
4. Load Excel.                                  [x]
5. Normalize schema/text.                       [x]
6. Save POIs.                                   [x]
```

Implementation:

```text
app/database/models.py, app/database/session.py
alembic.ini, migrations/env.py, migrations/versions/b92ab8d728b4_create_core_tables.py
app/tasco_data/config/settings.py
app/tasco_data/io/read_source.py, app/tasco_data/io/db.py
app/tasco_data/stages/s1_extract.py, app/tasco_data/stages/s2_normalize.py
app/tasco_data/pipeline.py (run_phase1), app/tasco_data/__main__.py
```

Verified: `python -m app.tasco_data --phase 1` upserts 111/111 POIs from
`data/raw/ai_maps_track2_dataset_participants.xlsx`, idempotent re-run confirmed.

## Phase 2 — Dynamic taxonomy — ✅ Done (2026-07-10), verified end-to-end with real OPENAI_API_KEY

```text
1. Seed minimal taxonomy_aliases.               [x]
2. Build alias resolver.                        [x]
3. Detect unknown values.                        [x]
4. Add LiteLLM taxonomy normalization.           [x]
5. Save LLM mappings back to taxonomy_aliases.   [x]
```

Implementation:

```text
app/tasco_data/taxonomy/seed_data.py, app/tasco_data/taxonomy/seed.py
app/tasco_data/taxonomy/resolver.py, app/tasco_data/taxonomy/unknown.py
app/tasco_data/llm/litellm_service.py, app/tasco_data/llm/prompts.py
app/tasco_data/taxonomy/normalize_llm.py
app/tasco_data/pipeline.py (run_phase2), app/tasco_data/__main__.py (--phase 2)
```

Also added: `attributes_raw` / `tags_raw` extraction in `s1_extract.py`
(semicolon-split raw `attributes`/`tags` columns) so attribute/tag values can
be resolved against `taxonomy_aliases` like category/location.

Verified: seeding is idempotent (41 aliases: 15 category, 17 attribute, 9
intent), unknown detection against the real dataset correctly finds 5/12
categories, 26 city+district values, 73 attribute values, 94 tag values not
covered by the seed (198 total).

Ran `python -m app.tasco_data --phase 2` for real against `openai/gpt-4o` with
`OPENAI_API_KEY` set: 178/198 unknown values were normalized and saved to
`taxonomy_aliases` (table now has 219 rows: 41 manual_seed +
178 llm_taxonomy_normalization). Remaining 20 unresolved
(`attribute`: 13, `location`: 5, `tag`: 2) were rejected by the confidence/
schema validation guardrail (§19.2) — expected behavior, not a bug. Re-running
`--phase 2` is idempotent and will retry only the still-unknown values.

## Phase 3 — Signals and enrichment — ✅ Done (2026-07-10), verified end-to-end with real OPENAI_API_KEY

```text
1. Generate deterministic base signals.               [x]
2. Add LiteLLM signal & intent enrichment.             [x]
3. Validate LLM output.                                [x]
4. Save accepted signals.                              [x]
5. Save semantic_summary to enrichment_json.           [x]
```

Implementation:

```text
app/tasco_data/signals/base.py (generate_deterministic_base_signals)
app/tasco_data/signals/db.py (upsert_poi_signals, save_enrichment_summaries)
app/tasco_data/llm/prompts.py (SIGNAL_ENRICHMENT_PROMPT)
app/tasco_data/signals/enrich_llm.py (validate_enriched_signals, enrich_pois_with_litellm)
app/tasco_data/pipeline.py (run_phase3), app/tasco_data/__main__.py (--phase 3)
```

Deterministic base signals (Step 9) reuse the Phase 2 `AliasCache`/`resolve()` to turn
`category_norm`, `city_norm`/`district_norm`, and per-item `attributes_raw`/`tags_raw`
into canonical `signal_norm` values (falling back to a snake_cased raw value if still
unresolved), plus the three explicit rule signals from §14.2: `is_24_7` → `open_24_7`
(time, hard), `rating >= 4.5` → `high_rating` (quality, inferred), `price_level <= 2` →
`budget_friendly` (price, inferred). LLM signal enrichment batches multiple POIs per
call (`LLM_SIGNAL_BATCH_SIZE`, default 10) instead of one call per POI, to control cost
per §19.1 while still matching the plan's "for each POI or batch of POIs" wording.
Guardrails (§19.2) reject signals with missing `evidence_text`, `confidence < 0.75`,
invalid `signal_type`/`constraint_default`, or a non-snake_case `signal_norm`.

Verified: mocked-LLM run (rollback after) confirmed the validate/save path rejects
low-confidence and non-snake_case signals correctly with no DB pollution.

Ran `python -m app.tasco_data --phase 3` for real against `openai/gpt-4o` with
`OPENAI_API_KEY` set, over all 111 POIs: `poi_signals` now has 1355 rows (1285
`rule_generated` + 70 `llm_signal_enrichment`, spanning `attribute` (425), `tag` (395),
`location` (222), `category` (111), `intent` (69), `price` (62), `quality` (36),
`time` (35)). 71/111 POIs received a `semantic_summary` in `pois.enrichment_json`.
Sampled LLM-inferred intents (`work_or_study`, `date_night`, `tourist_checkin`,
`social_meeting`, `group_outing`) all carry sensible Vietnamese `evidence_text` tied to
each POI's actual description/attributes. Re-running `--phase 3` is idempotent
(`on_conflict_do_nothing` on `uq_poi_signal_unique`).

## Phase 4 — Search documents — ✅ Done (2026-07-10), verified end-to-end against real Postgres data

```text
1. Build semantic_text.                                [x]
2. Build keyword_text.                                 [x]
3. Build full_semantic document.                       [x]
4. Build signal_intent document.                       [x]
5. Build name_location document.                       [x]
```

Implementation:

```text
app/tasco_data/search_documents/build_text.py (build_semantic_text, build_keyword_text)
app/tasco_data/search_documents/build_docs.py (build_search_documents)
app/tasco_data/search_documents/db.py (save_pois_text, upsert_search_documents)
app/tasco_data/pipeline.py (run_phase4), app/tasco_data/__main__.py (--phase 4)
```

Unlike Phase 1-3, Phase 4 reads its source directly from Postgres (`pois` joined with
`poi_signals` via the ORM relationship, `selectinload(Poi.signals)`) instead of
re-reading the Excel file, since it depends on data only available after Phase 2/3 have
run (resolved `*_norm` fields, `poi_signals`, `enrichment_json.semantic_summary`) — this
matches §2.4's `pois + poi_signals → build content` data flow.

Step 11 builds `semantic_text` (POI name/brand/category/sub_category/location/
description + signal names + `semantic_summary`) and `keyword_text` (normalized fields +
`signal_norm` values) and saves them to `pois`. Step 12 builds three
`poi_search_documents` rows per POI: `{poi_id}::full_semantic` (semantic_text/
keyword_text), `{poi_id}::signal_intent` (intent signals with evidence_text + other
signal_norms), and `{poi_id}::name_location` (name/brand/address/district/city only).
`upsert_search_documents` uses `on_conflict_do_update` on `doc_id` (not `do_nothing`
like the Phase 3 signal upsert), since these documents are fully recomputed derived data
and must refresh on rerun rather than accumulate.

Ran `python -m app.tasco_data --phase 4` against the real dev Postgres (111 POIs from
Phase 1-3): all 111 `pois` rows got `semantic_text`/`keyword_text`, and
`poi_search_documents` now has 333 rows (111 `full_semantic` + 111 `signal_intent` + 111
`name_location`). Spot-checked `C001`: `semantic_text` combines name, category,
location, description, signal names (`work_or_study, Cafe, Wifi, Quiet, ...`), and its
LLM `semantic_summary`; `signal_intent` doc correctly separates the `work_or_study`
intent (with Vietnamese evidence_text) from other signals. Re-ran `--phase 4` a second
time to confirm idempotency: same counts (333 documents, no duplicates), confirming the
`on_conflict_do_update` upsert works correctly.

## Phase 5 — Embedding + Qdrant

```text
1. Load BGE-M3.
2. Generate dense embeddings.
3. Create Qdrant collection.
4. Upsert vectors with payload.
5. Validate Qdrant ↔ Postgres join.
```

---

# 22. Final summary

Final design:

```text
PostgreSQL:
1. pois
2. poi_signals
3. taxonomy_aliases
4. poi_search_documents

LLM:
- LiteLLM
- default model: openai/gpt-4o
- used only offline

LLM call points:
1. unknown taxonomy normalization
2. opening_hours fallback when parser fails
3. signal & intent enrichment

No LLM:
- basic schema normalization
- basic text normalization
- deterministic base signals
- BGE-M3 embedding
- Qdrant upsert
- online search default
```

Thiết kế này giúp hệ thống:

```text
- không overfit public dataset
- tự học thêm taxonomy từ dataset mới
- cache kết quả LLM vào DB
- tránh gọi LLM lặp lại
- giữ online search nhanh
- vẫn có evidence rõ ràng cho rerank/explanation
```

---

# 23. References

- LiteLLM Getting Started: https://docs.litellm.ai/docs/
- LiteLLM GitHub: https://github.com/BerriAI/litellm
- SQLAlchemy PostgreSQL dialect: https://docs.sqlalchemy.org/en/latest/dialects/postgresql.html
- Qdrant filtering: https://qdrant.tech/documentation/search/filtering/
- BGE-M3 documentation: https://bge-model.com/bge/bge_m3.html
