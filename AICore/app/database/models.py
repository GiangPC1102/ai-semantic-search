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
