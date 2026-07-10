"""Schema đầu ra cho pipeline Query Understanding."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RankingSignalType(str, Enum):
    """Tín hiệu ranking canonical — khớp ``ranking_signals_new.csv``."""

    MIXED_LANGUAGE = "mixed_language"
    OPENING_HOURS = "opening_hours"
    PRICE = "price"
    POPULARITY = "popularity"
    LOCATION = "location"
    CATEGORY = "category"
    ATTRIBUTE = "attribute"
    ATTRIBUTES = "attributes"
    SEMANTIC = "semantic"
    RATING = "rating"
    REVIEW = "review"


class OpeningHoursPreference(BaseModel):
    """Desired opening-hours constraint — used with signal ``opening_hours``."""

    open_time: str | None = Field(
        default=None,
        description=(
            "Time the POI must already be open / must have opened by, HH:MM 24h. "
            "Use for 'mở / mở lúc / mở cửa lúc / opens at / opens from / opens after' "
            "(e.g. '04:00' for 'Cây ATM mở 4h' or 'mở cửa lúc 4h'). "
            "Do NOT use for 'còn mở / still open at'."
        ),
    )
    close_time: str | None = Field(
        default=None,
        description=(
            "Time the POI must still be open / remain open until, HH:MM 24h. "
            "Use for 'còn mở lúc / still open at / open until / open late' "
            "(e.g. '23:00' for 'còn mở lúc 23:00', '02:00' for 'mở đến 2h sáng')."
        ),
    )
    is_24h: bool = Field(
        default=False,
        description="Requires 24/7 opening",
    )

    @field_validator("open_time", "close_time", mode="before")
    @classmethod
    def coerce_time(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value).strip()

    @field_validator("is_24h", mode="before")
    @classmethod
    def coerce_is_24h(cls, value: Any) -> bool:
        return bool(value) if value is not None else False


class HardFilters(BaseModel):
    """Hard-attribute dùng để lọc cứng trước khi ranking.

    Giá trị ``null`` nghĩa là không extract được từ truy vấn.
    Tên field khớp cột POI: brand, category, sub_category, city, district.
    """

    brand: str | None = Field(
        default=None,
        description="Canonical brand name, e.g. Highlands Coffee",
    )
    category: str | None = Field(
        default=None,
        description="Top-level POI type, e.g. Quán cà phê, Nhà hàng",
    )
    subcategory: str | None = Field(
        default=None,
        description="Second-level POI type, e.g. Coffee Chain, Specialty Coffee",
    )
    city: str | None = Field(
        default=None,
        description="City, e.g. TP.HCM, Hà Nội, Đà Nẵng",
    )
    district: str | None = Field(
        default=None,
        description="District, e.g. Quận 1, Hoàn Kiếm",
    )


class RankingSignalItem(BaseModel):
    """Một tín hiệu ranking được phát hiện từ truy vấn."""

    signal: RankingSignalType
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    opening_hours: OpeningHoursPreference | None = Field(
        default=None,
        description=(
            "Opening-hours details — ONLY when signal is opening_hours; "
            "must be null/omitted for all other signals"
        ),
    )

    @model_validator(mode="after")
    def drop_opening_hours_unless_signal(self) -> RankingSignalItem:
        """Strip opening_hours unless signal is opening_hours."""
        if self.signal != RankingSignalType.OPENING_HOURS and self.opening_hours is not None:
            return self.model_copy(update={"opening_hours": None})
        return self


class QueryUnderstandOutput(BaseModel):
    """Kết quả cuối cùng của pipeline Query Understanding."""

    original_query: str = Field(description="Raw user query")
    normalized_query: str = Field(
        description=(
            "Normalized query: diacritics fixed, abbreviations expanded, language unified"
        ),
    )
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    ranking_signals: list[RankingSignalItem] = Field(default_factory=list)


class LLMQueryUnderstandPayload(BaseModel):
    """Payload JSON mà LLM trả về — map sang ``QueryUnderstandOutput`` sau post-process."""

    normalized_query: str = ""
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    ranking_signals: list[RankingSignalItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_nulls(cls, data: Any) -> Any:
        """Chuẩn hóa các field null phổ biến từ LLM trước khi validate."""
        if not isinstance(data, dict):
            return data

        data.pop("soft_hints", None)
        data.pop("semantic_query", None)
        data.pop("language", None)

        if data.get("normalized_query") is None:
            data["normalized_query"] = ""
        if data.get("hard_filters") is None:
            data["hard_filters"] = {}
        if data.get("ranking_signals") is None:
            data["ranking_signals"] = []

        return data

    @field_validator("normalized_query", mode="before")
    @classmethod
    def coerce_normalized_query(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("ranking_signals", mode="before")
    @classmethod
    def coerce_ranking_signals(cls, value: Any) -> list[Any]:
        return [] if value is None else value


class QueryUnderstandRequest(BaseModel):
    """Request body cho endpoint query understanding."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language POI search query",
        examples=["tìm kiếm cho tôi quán cafe Highland ở Quận 1"],
    )
