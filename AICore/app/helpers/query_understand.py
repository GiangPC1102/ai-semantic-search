"""Pipeline Query Understanding — extract hard-filter & ranking signals from POI query."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.logger import logger
from app.prompts.main import build_backbone_messages, build_specialist_messages
from app.schemas.signal_ranking import (
    BackbonePayload,
    HardFilters,
    OpeningHoursPreference,
    QueryUnderstandOutput,
    RankingSignalItem,
    RankingSignalType,
    SPECIALIST_SIGNALS,
    SpecialistPayload,
)
from app.utils.llm_partern import LLM, LLMError

_BACKBONE_SCHEMA_HINT = BackbonePayload.model_json_schema()
_SPECIALIST_SCHEMA_HINT = SpecialistPayload.model_json_schema()


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

        backbone, specialist = self._extract_both(preprocessed)
        output = self._merge(query_input, preprocessed, backbone, specialist)
        return self._post_process(output)

    @staticmethod
    def _preprocess_query(query: str) -> str:
        """Tiền xử lý nhẹ trước khi gửi LLM: trim và gộp khoảng trắng."""
        return re.sub(r"\s+", " ", query.strip())

    def _extract_both(
        self,
        query: str,
    ) -> tuple[BackbonePayload, SpecialistPayload]:
        """Chạy song song 2 LLM call (backbone + specialist).

        Backbone là bắt buộc — nếu fail thì raise. Specialist là tùy chọn — nếu fail
        thì log + trả SpecialistPayload rỗng (degrade gracefully, vẫn có backbone).
        """
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_backbone = executor.submit(self._extract_backbone, query)
            future_specialist = executor.submit(self._extract_specialist, query)

            backbone = future_backbone.result()  # fatal nếu backbone fail
            try:
                specialist = future_specialist.result()
            except QueryUnderstandError as exc:
                logger.warning(
                    "Specialist extraction failed; proceeding without specialist: %s",
                    exc,
                )
                specialist = SpecialistPayload()
        return backbone, specialist

    def _extract_backbone(self, query: str) -> BackbonePayload:
        """Gọi LLM backbone và parse JSON response."""
        messages = build_backbone_messages(query, _BACKBONE_SCHEMA_HINT)
        return self._parse_payload(self._call_llm(messages), BackbonePayload, "backbone")

    def _extract_specialist(self, query: str) -> SpecialistPayload:
        """Gọi LLM specialist (0-or-1) và parse JSON response."""
        messages = build_specialist_messages(query, _SPECIALIST_SCHEMA_HINT)
        return self._parse_payload(self._call_llm(messages), SpecialistPayload, "specialist")

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """Gọi LLM với json_object response format, trả raw content."""
        try:
            response = self._llm.chat(
                messages,
                response_format={"type": "json_object"},
            )
        except LLMError as exc:
            raise QueryUnderstandError(f"LLM extraction thất bại: {exc}") from exc
        return response.content

    @staticmethod
    def _parse_payload(
        content: str,
        model: type[BaseModel],
        label: str,
    ) -> BaseModel:
        """Parse và validate JSON từ LLM thành model đã cho."""
        try:
            raw: dict[str, Any] = json.loads(content)
            return model.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Parse LLM %s payload failed: %s | content=%s",
                label,
                exc,
                content,
            )
            raise QueryUnderstandError(
                f"Không parse được JSON từ LLM ({label}): {exc}"
            ) from exc

    @staticmethod
    def _merge(
        original_query: str,
        preprocessed_query: str,
        backbone: BackbonePayload,
        specialist: SpecialistPayload,
    ) -> QueryUnderstandOutput:
        """Merge backbone + specialist thành output schema đầy đủ."""

        signals = [
            item
            for item in backbone.ranking_signals
            if item.signal not in SPECIALIST_SIGNALS
        ]
        if specialist.signal is not None:
            signals.append(
                RankingSignalItem(
                    signal=specialist.signal,
                    confidence=specialist.confidence,
                )
            )

        normalized_query = backbone.normalized_query.strip() or preprocessed_query
        return QueryUnderstandOutput(
            original_query=original_query,
            normalized_query=normalized_query,
            language=backbone.language,
            hard_filters=backbone.hard_filters,
            ranking_signals=signals,
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
        """Chuẩn hóa thời gian về format HH:MM; bỏ giá trị không hợp lệ."""
        if not value:
            return None

        cleaned = value.strip()
        match = re.match(r"^(\d{1,2}):(\d{1,2})$", cleaned)
        if not match:
            return None

        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return None
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
        """Chuẩn hóa opening_hours; chỉ giữ trên signal opening_hours."""
        updated: list[RankingSignalItem] = []
        for item in signals:
            if item.signal != RankingSignalType.OPENING_HOURS:
                if item.opening_hours is None:
                    updated.append(item)
                else:
                    updated.append(item.model_copy(update={"opening_hours": None}))
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
