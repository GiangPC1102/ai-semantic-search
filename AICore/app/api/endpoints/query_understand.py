from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.helpers.query_understand import QueryUnderstandError, QueryUnderstander
from app.schemas.signal_ranking import QueryUnderstandOutput, QueryUnderstandRequest

router = APIRouter()


@router.post("/understand", response_model=QueryUnderstandOutput)
async def understand_query(body: QueryUnderstandRequest) -> QueryUnderstandOutput:
    """Phân tích truy vấn POI — extract hard-filter và ranking signals."""
    understander = QueryUnderstander()
    try:
        return await understander.aunderstand(body.query)
    except QueryUnderstandError as exc:
        message = str(exc)
        if "rỗng" in message.lower():
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=502, detail=message) from exc
