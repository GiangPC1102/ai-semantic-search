from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import Poi

_UPDATE_COLUMNS = [
    "poi_name",
    "poi_name_norm",
    "brand",
    "brand_norm",
    "category",
    "category_norm",
    "sub_category",
    "sub_category_norm",
    "city",
    "city_norm",
    "district",
    "district_norm",
    "address",
    "address_norm",
    "latitude",
    "longitude",
    "rating",
    "review_count",
    "popularity_score",
    "price_level",
    "opening_hours_raw",
    "is_24_7",
    "description",
    "description_norm",
]


_POI_COLUMNS = {"poi_id", *_UPDATE_COLUMNS}


def upsert_pois(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0

    poi_rows = [{k: v for k, v in row.items() if k in _POI_COLUMNS} for row in rows]

    stmt = insert(Poi).values(poi_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Poi.poi_id],
        set_={col: getattr(stmt.excluded, col) for col in _UPDATE_COLUMNS},
    )
    session.execute(stmt)
    return len(rows)
