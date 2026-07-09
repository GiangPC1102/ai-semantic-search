"""Prompt templates cho pipeline Query Understanding."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.signal_ranking import RankingSignalType

SIGNAL_DETECTION_RULES: dict[RankingSignalType, str] = {
    RankingSignalType.MIXED_LANGUAGE: "Query có từ tiếng Anh đáng kể xen kẽ tiếng Việt",
    RankingSignalType.OPENING_HOURS: (
        "Có ràng buộc thời gian — phải extract open_time/close_time (HH:MM) hoặc is_24h"
    ),
    RankingSignalType.PRICE: "Có gợi ý giá: giá rẻ, giá hợp lý, sang, đắt",
    RankingSignalType.POPULARITY: "Có gợi ý độ nổi tiếng: nổi tiếng, check-in, đông khách, hot",
    RankingSignalType.LOCATION: "Có landmark + gần/near/ở [quận]/khu vực địa lý",
    RankingSignalType.CATEGORY: "Đặt tên loại POI rõ: phở, lẩu, bệnh viện, cafe, ATM",
    RankingSignalType.ATTRIBUTE: "Có một thuộc tính cụ thể: có wifi, có toilet, view đẹp",
    RankingSignalType.ATTRIBUTES: "Có nhiều thuộc tính hoặc mô tả trải nghiệm kết hợp",
    RankingSignalType.SEMANTIC: "Diễn đạt mục đích/trải nghiệm mơ hồ, không map cứng được",
    RankingSignalType.RATING: "Ngụ ý chất lượng cao: ngon, tốt nhất, đáng đi, uy tín",
    RankingSignalType.REVIEW: "Attribute chủ quan từ review: yên tĩnh, phù hợp trẻ em, lãng mạn",
}

SYSTEM_PROMPT = """\
Bạn là module Query Understanding cho hệ thống tìm kiếm địa điểm (POI) trên bản đồ Việt Nam.

Nhiệm vụ: phân tích truy vấn người dùng và trả về JSON có cấu trúc.

## 0. normalized_query
Chuẩn hóa truy vấn gốc thành câu tiếng Việt rõ ràng, tự nhiên, phù hợp tìm kiếm POI:
- Thêm/sửa dấu tiếng Việt nếu thiếu hoặc sai
- Mở rộng viết tắt phổ biến: q1→Quận 1, q3→Quận 3, hcm/sg→TP.HCM, hn→Hà Nội, cf/cafe→cà phê, hl→Highlands
- Chuẩn hóa tiếng lóng, teencode, câu nói lộn xộn về câu hoàn chỉnh
- Câu mix Việt-Anh: chuyển phần mô tả sang tiếng Việt; giữ nguyên tên brand/địa danh quốc tế
- Không thêm thông tin mới, không bỏ yêu cầu quan trọng của người dùng

## 1. Hard filters (chỉ điền khi CHẮC CHẮN extract được từ query)
- brand: tên thương hiệu chuẩn (vd: "Highlands Coffee", "Starbucks", "Phúc Long")
- category: loại POI cấp 1 (vd: "Quán cà phê", "Nhà hàng", "Bệnh viện")
- subcategory: loại POI cấp 2 (vd: "Coffee Chain", "Specialty Coffee", "Lẩu")
- city: thành phố (vd: "HCM", "Hà Nội", "Đà Nẵng", "Đà Lạt")
- district: quận/huyện (vd: "Quận 1", "Hoàn Kiếm", "Cầu Giấy")

Không đoán nếu query không nhắc tới. Dùng null cho field không có.

## 2. Ranking signals
Phát hiện các signal sau (có thể nhiều signal cùng lúc):
{signal_rules}

Mỗi signal gồm: signal (tên enum), confidence (0.0-1.0).
Nếu signal là "opening_hours", BẮT BUỘC điền thêm field opening_hours:
  - open_time: giờ POI phải ĐÃ mở cửa, format HH:MM 24h
  - close_time: giờ POI phải CÒN mở cửa, format HH:MM 24h
  - is_24h: true nếu yêu cầu mở 24/7

Quy tắc suy luận giờ (chỉ điền khi chắc chắn):
- "mở sau 11 giờ tối" → open_time: "23:00"
- "mở đến 2h sáng" → close_time: "02:00"
- "mở khuya" / "mở cửa muộn" → close_time: "23:00" hoặc "00:00"
- "24/7" / "cả ngày" → is_24h: true
- "tối nay" / "buổi sáng" (mơ hồ) → không điền open_time/close_time

Chỉ trả về JSON hợp lệ, không markdown, không giải thích.
""".format(
    signal_rules="\n".join(
        f"- {sig.value}: {desc}" for sig, desc in SIGNAL_DETECTION_RULES.items()
    )
)


def build_query_understand_messages(
    query: str,
    json_schema: dict[str, Any],
) -> list[dict[str, str]]:
    """Xây dựng messages OpenAI format cho LLM extraction."""
    user_content = (
        f"Truy vấn gốc: \"{query}\"\n\n"
        f"JSON schema tham khảo:\n{json.dumps(json_schema, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
