"""Tiện ích parse và so khớp giờ mở cửa POI với ràng buộc từ query understanding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.signal_ranking import OpeningHoursPreference

MINUTES_PER_DAY = 24 * 60
_HHMM_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")
_RANGE_PATTERN = re.compile(
    r"^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$",
)
_OPEN_KEYS = ("open_time", "open", "from", "start", "opens")
_CLOSE_KEYS = ("close_time", "close", "to", "end", "closes")
_24H_MARKERS = ("24/7", "24h", "24 giờ", "cả ngày")


@dataclass(frozen=True)
class ParsedOpenHours:
    """Giờ mở/đóng của POI đã chuẩn hóa về phút trong ngày."""

    open_minutes: int
    close_minutes: int
    is_24h: bool = False


def parse_hhmm_to_minutes(value: str) -> int | None:
    """Chuyển chuỗi HH:MM thành số phút kể từ 00:00."""
    match = _HHMM_PATTERN.match(value.strip())
    if not match:
        return None

    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def parse_open_hours(raw: Any) -> ParsedOpenHours | None:
    """Parse ``open_hours`` JSON/string từ database sang cấu trúc chuẩn."""
    if raw is None:
        return None

    if isinstance(raw, str):
        return _parse_open_hours_string(raw)

    if isinstance(raw, dict):
        return _parse_open_hours_dict(raw)

    return None


def is_open_at(minute_of_day: int, schedule: ParsedOpenHours) -> bool:
    """Kiểm tra POI có đang mở tại ``minute_of_day`` hay không."""
    if schedule.is_24h:
        return True

    open_at = schedule.open_minutes
    close_at = schedule.close_minutes

    if open_at == close_at:
        return True

    if close_at > open_at:
        return open_at <= minute_of_day < close_at

    return minute_of_day >= open_at or minute_of_day < close_at


def matches_opening_hours_preference(
    raw_open_hours: Any,
    preference: OpeningHoursPreference,
) -> bool:
    """So khớp giờ mở cửa POI với ràng buộc từ signal ``opening_hours``."""
    has_constraint = (
        preference.is_24h
        or preference.open_time is not None
        or preference.close_time is not None
    )
    if not has_constraint:
        return True

    schedule = parse_open_hours(raw_open_hours)
    if schedule is None:
        return False

    if preference.is_24h:
        return schedule.is_24h

    if preference.open_time:
        open_minutes = parse_hhmm_to_minutes(preference.open_time)
        if open_minutes is None or not is_open_at(open_minutes, schedule):
            return False

    if preference.close_time:
        close_minutes = parse_hhmm_to_minutes(preference.close_time)
        if close_minutes is None or not is_open_at(close_minutes, schedule):
            return False

    return True


def _parse_open_hours_string(value: str) -> ParsedOpenHours | None:
    """Parse chuỗi dạng ``07:00-22:30`` hoặc ``24/7``."""
    cleaned = value.strip()
    lowered = cleaned.lower()

    if any(marker in lowered for marker in _24H_MARKERS):
        return ParsedOpenHours(open_minutes=0, close_minutes=MINUTES_PER_DAY - 1, is_24h=True)

    match = _RANGE_PATTERN.match(cleaned)
    if not match:
        return None

    open_minutes = parse_hhmm_to_minutes(match.group(1))
    close_minutes = parse_hhmm_to_minutes(match.group(2))
    if open_minutes is None or close_minutes is None:
        return None

    return ParsedOpenHours(
        open_minutes=open_minutes,
        close_minutes=close_minutes,
        is_24h=_is_24h_range(open_minutes, close_minutes),
    )


def _parse_open_hours_dict(data: dict[str, Any]) -> ParsedOpenHours | None:
    """Parse object JSON lưu trong cột ``open_hours``."""
    if data.get("is_24h") is True:
        return ParsedOpenHours(open_minutes=0, close_minutes=MINUTES_PER_DAY - 1, is_24h=True)

    open_raw = _pick_value(data, _OPEN_KEYS)
    close_raw = _pick_value(data, _CLOSE_KEYS)

    if open_raw is None and close_raw is None:
        raw_text = data.get("text") or data.get("value")
        if isinstance(raw_text, str):
            return _parse_open_hours_string(raw_text)
        return None

    open_minutes = parse_hhmm_to_minutes(str(open_raw)) if open_raw else None
    close_minutes = parse_hhmm_to_minutes(str(close_raw)) if close_raw else None
    if open_minutes is None or close_minutes is None:
        return None

    return ParsedOpenHours(
        open_minutes=open_minutes,
        close_minutes=close_minutes,
        is_24h=_is_24h_range(open_minutes, close_minutes),
    )


def _pick_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    """Lấy giá trị đầu tiên khớp một trong các key."""
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _is_24h_range(open_minutes: int, close_minutes: int) -> bool:
    """Heuristic nhận diện POI mở 24/7."""
    return (
        open_minutes == 0
        and close_minutes in {MINUTES_PER_DAY - 1, MINUTES_PER_DAY}
    ) or open_minutes == close_minutes
