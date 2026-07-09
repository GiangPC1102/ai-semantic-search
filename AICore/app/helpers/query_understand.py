"""Pipeline Query Understanding — extract hard-filter & ranking signals từ truy vấn POI."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.core.logger import logger
from app.prompts.main import build_query_understand_messages
from app.schemas.signal_ranking import (
    HardFilters,
    LLMQueryUnderstandPayload,
    OpeningHoursPreference,
    QueryUnderstandOutput,
    RankingSignalItem,
    RankingSignalType,
)
from app.utils.llm_partern import LLM, LLMError

_JSON_SCHEMA_HINT = LLMQueryUnderstandPayload.model_json_schema()


class QueryUnderstandError(Exception):
    """Lỗi trong pipeline query understanding."""


class QueryUnderstander:
    """Pipeline phân tích truy vấn POI qua LLM + post-process."""

    def __init__(self, llm: LLM | None = None) -> None:
        self._llm = llm or LLM(temperature=0.1)

    def understand(self, query_input: str) -> QueryUnderstandOutput:
        """Phân tích truy vấn và trả về object có cấu trúc.

        Args:
            query_input: Câu truy vấn tự nhiên của người dùng.

        Returns:
            QueryUnderstandOutput với hard-filter và ranking signals.
        """
        preprocessed = self._preprocess_query(query_input)
        if not preprocessed:
            raise QueryUnderstandError("Truy vấn rỗng")

        payload = self._extract_with_llm(preprocessed)
        output = self._build_output(query_input, preprocessed, payload)
        return self._post_process(output)

    async def aunderstand(self, query_input: str) -> QueryUnderstandOutput:
        """Phiên bản async của ``understand``."""
        preprocessed = self._preprocess_query(query_input)
        if not preprocessed:
            raise QueryUnderstandError("Truy vấn rỗng")

        payload = await self._aextract_with_llm(preprocessed)
        output = self._build_output(query_input, preprocessed, payload)
        return self._post_process(output)

    @staticmethod
    def _preprocess_query(query: str) -> str:
        """Tiền xử lý nhẹ trước khi gửi LLM: trim và gộp khoảng trắng."""
        return re.sub(r"\s+", " ", query.strip())

    def _extract_with_llm(self, query: str) -> LLMQueryUnderstandPayload:
        """Gọi LLM và parse JSON response."""
        messages = self._build_messages(query)
        try:
            response = self._llm.chat(
                messages,
                response_format={"type": "json_object"},
            )
        except LLMError as exc:
            raise QueryUnderstandError(f"LLM extraction thất bại: {exc}") from exc

        return self._parse_llm_payload(response.content)

    async def _aextract_with_llm(self, query: str) -> LLMQueryUnderstandPayload:
        """Gọi LLM async và parse JSON response."""
        messages = self._build_messages(query)
        try:
            response = await self._llm.achat(
                messages,
                response_format={"type": "json_object"},
            )
        except LLMError as exc:
            raise QueryUnderstandError(f"LLM extraction thất bại: {exc}") from exc

        return self._parse_llm_payload(response.content)

    def _build_messages(self, query: str) -> list[dict[str, str]]:
        """Xây dựng prompt cho LLM."""
        return build_query_understand_messages(query, _JSON_SCHEMA_HINT)

    @staticmethod
    def _parse_llm_payload(content: str) -> LLMQueryUnderstandPayload:
        """Parse và validate JSON từ LLM."""
        try:
            raw: dict[str, Any] = json.loads(content)
            return LLMQueryUnderstandPayload.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error("Parse LLM query understand payload failed: %s | content=%s", exc, content)
            raise QueryUnderstandError(f"Không parse được JSON từ LLM: {exc}") from exc

    @staticmethod
    def _build_output(
        original_query: str,
        preprocessed_query: str,
        payload: LLMQueryUnderstandPayload,
    ) -> QueryUnderstandOutput:
        """Map LLM payload sang output schema đầy đủ."""
        normalized_query = payload.normalized_query.strip() or preprocessed_query
        return QueryUnderstandOutput(
            original_query=original_query,
            normalized_query=normalized_query,
            hard_filters=payload.hard_filters,
            ranking_signals=payload.ranking_signals,
        )

    def _post_process(self, output: QueryUnderstandOutput) -> QueryUnderstandOutput:
        """Chuẩn hóa hard-filter, opening hours trên signals và dedupe."""
        hard_filters = self._normalize_hard_filters(output.hard_filters)
        ranking_signals = self._normalize_signal_opening_hours(
            self._dedupe_signals(output.ranking_signals),
        )

        if not ranking_signals:
            ranking_signals.append(
                RankingSignalItem(
                    signal=RankingSignalType.SEMANTIC,
                    confidence=0.5,
                )
            )

        return output.model_copy(
            update={
                "hard_filters": hard_filters,
                "ranking_signals": sorted(
                    ranking_signals,
                    key=lambda item: item.confidence,
                    reverse=True,
                ),
            }
        )

    @staticmethod
    def _normalize_hhmm(value: str | None) -> str | None:
        """Chuẩn hóa thời gian về format HH:MM."""
        if not value:
            return None

        cleaned = value.strip()
        match = re.match(r"^(\d{1,2}):(\d{1,2})$", cleaned)
        if not match:
            return cleaned

        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return cleaned
        return f"{hour:02d}:{minute:02d}"

    @classmethod
    def _normalize_opening_hours(
        cls,
        opening_hours: OpeningHoursPreference | None,
    ) -> OpeningHoursPreference | None:
        """Chuẩn hóa open_time/close_time về HH:MM."""
        if opening_hours is None:
            return None

        normalized = opening_hours.model_copy(
            update={
                "open_time": cls._normalize_hhmm(opening_hours.open_time),
                "close_time": cls._normalize_hhmm(opening_hours.close_time),
            }
        )

        if (
            not normalized.open_time
            and not normalized.close_time
            and not normalized.is_24h
        ):
            return None
        return normalized

    @classmethod
    def _normalize_signal_opening_hours(
        cls,
        signals: list[RankingSignalItem],
    ) -> list[RankingSignalItem]:
        """Chuẩn hóa opening_hours trên signal opening_hours."""
        updated: list[RankingSignalItem] = []
        for item in signals:
            if item.signal != RankingSignalType.OPENING_HOURS or not item.opening_hours:
                updated.append(item)
                continue
            updated.append(
                item.model_copy(
                    update={
                        "opening_hours": cls._normalize_opening_hours(item.opening_hours),
                    }
                )
            )
        return updated

    @staticmethod
    def _normalize_hard_filters(filters: HardFilters) -> HardFilters:
        """Chuẩn hóa giá trị hard-filter."""
        data = filters.model_dump()

        for key, value in data.items():
            if isinstance(value, str):
                cleaned = value.strip()
                data[key] = cleaned if cleaned else None

        return HardFilters.model_validate(data)

    @staticmethod
    def _dedupe_signals(signals: list[RankingSignalItem]) -> list[RankingSignalItem]:
        """Gộp signal trùng loại, giữ confidence cao nhất."""
        best: dict[RankingSignalType, RankingSignalItem] = {}
        for item in signals:
            existing = best.get(item.signal)
            if existing is None or item.confidence > existing.confidence:
                best[item.signal] = item
        return list(best.values())
