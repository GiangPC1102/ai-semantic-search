"""API lọc POI theo hard-filter từ query understanding."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from prisma.models import Poi

from app.core.database import get_store
from app.schemas.poi import BrandSummary, PoiFilterRequest, PoiFilterResponse, PoiItem
from app.services.store import StoreError

router = APIRouter()


def _to_poi_item(poi: Poi) -> PoiItem:
    """Map Prisma POI model sang response schema."""
    brand_summary: BrandSummary | None = None
    if poi.brand is not None:
        brand_summary = BrandSummary(
            id=poi.brand.id,
            name=poi.brand.name,
            category=poi.brand.category,
            subcategory=poi.brand.subcategory,
        )

    return PoiItem(
        id=poi.id,
        name=poi.name,
        city=poi.city,
        district=poi.district,
        address=poi.address,
        longitude=poi.longitude,
        latitude=poi.latitude,
        rating=poi.rating,
        review_count=poi.reviewCount,
        popularity_score=poi.popularityScore,
        price_level=poi.priceLevel,
        open_hours=poi.openHours,
        description=poi.description,
        brand=brand_summary,
    )


@router.post("/filter", response_model=PoiFilterResponse)
async def filter_pois(body: PoiFilterRequest) -> PoiFilterResponse:
    """Lọc POI theo ``hard_filters`` và ``ranking_signals``.

  Ví dụ body:

  ```json
  {
    "hard_filters": {
      "district": "Quận 1",
      "category": "Nhà hàng"
    },
    "ranking_signals": [
      {
        "signal": "opening_hours",
        "confidence": 0.9,
        "opening_hours": {
          "close_time": "23:00"
        }
      }
    ]
  }
  ```
    """
    store = get_store()
    try:
        pois = await store.filter_hard_hint(body.hard_filters, body.ranking_signals)
    except StoreError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    items = [_to_poi_item(poi) for poi in pois]
    return PoiFilterResponse(count=len(items), items=items)
