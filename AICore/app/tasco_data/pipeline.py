import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import selectinload

from app.core.config import settings as core_settings
from app.database.models import Poi
from app.database.session import get_session
from app.tasco_data.config.settings import settings
from app.tasco_data.io.db import upsert_pois
from app.tasco_data.io.read_source import load_poi_dataset
from app.tasco_data.llm.litellm_service import LiteLLMService
from app.tasco_data.search_documents.build_docs import build_search_documents
from app.tasco_data.search_documents.build_text import build_semantic_text, build_keyword_text
from app.tasco_data.search_documents.db import save_pois_text, upsert_search_documents
from app.tasco_data.signals.base import generate_deterministic_base_signals
from app.tasco_data.signals.db import save_enrichment_summaries, upsert_poi_signals
from app.tasco_data.signals.enrich_llm import enrich_pois_with_litellm
from app.tasco_data.stages.s1_extract import normalize_schema
from app.tasco_data.stages.s2_normalize import normalize_text_fields
from app.tasco_data.taxonomy.normalize_llm import normalize_unknowns_with_litellm, save_taxonomy_aliases
from app.tasco_data.taxonomy.resolver import load_alias_cache
from app.tasco_data.taxonomy.seed import seed_minimal_taxonomy_aliases
from app.tasco_data.taxonomy.unknown import collect_unknowns

logger = logging.getLogger(__name__)


def _load_normalized_rows(file_path: Optional[str | Path], sheet_name: Optional[str]) -> list[dict]:
    resolved_path = Path(file_path) if file_path else settings.poi_dataset_abspath
    resolved_sheet = sheet_name or settings.poi_dataset_sheet

    logger.info("Loading POI dataset from %s (sheet=%s)", resolved_path, resolved_sheet)
    raw_rows = load_poi_dataset(resolved_path, resolved_sheet)

    normalized_rows = []
    for row in raw_rows:
        item = normalize_schema(row)
        item = normalize_text_fields(item)
        normalized_rows.append(item)

    return normalized_rows


def run_phase1(file_path: Optional[str | Path] = None, sheet_name: Optional[str] = None) -> int:
    normalized_rows = _load_normalized_rows(file_path, sheet_name)

    session = get_session()
    try:
        count = upsert_pois(session, normalized_rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("Upserted %d POIs into Postgres", count)
    return count


def run_phase2(file_path: Optional[str | Path] = None, sheet_name: Optional[str] = None) -> dict:
    normalized_rows = _load_normalized_rows(file_path, sheet_name)

    session = get_session()
    try:
        seed_minimal_taxonomy_aliases(session)
        session.commit()

        alias_cache = load_alias_cache(session)
        unknowns = collect_unknowns(normalized_rows, alias_cache)
        unknown_counts = {alias_type: len(values) for alias_type, values in unknowns.items()}
        logger.info("Unknown taxonomy values by type: %s", unknown_counts)

        saved_count = 0
        if settings.llm_taxonomy_enabled and unknowns:
            if not core_settings.OPENAI_API_KEY:
                logger.warning(
                    "LLM_TAXONOMY_ENABLED is true but OPENAI_API_KEY is not set; "
                    "skipping LiteLLM normalization for %d unknown value(s)",
                    sum(unknown_counts.values()),
                )
            else:
                existing_targets_by_type: dict[str, list[str]] = {}
                for (alias_type, _alias_norm), target in alias_cache.items():
                    existing_targets_by_type.setdefault(alias_type, [])
                    if target.target_id not in existing_targets_by_type[alias_type]:
                        existing_targets_by_type[alias_type].append(target.target_id)

                llm = LiteLLMService(model=core_settings.LLM_MODEL, temperature=core_settings.LLM_TEMPERATURE)
                mappings = normalize_unknowns_with_litellm(
                    unknowns,
                    llm,
                    existing_targets_by_type,
                    batch_size=settings.llm_batch_size,
                )
                saved_count = save_taxonomy_aliases(session, mappings)
                session.commit()

                alias_cache = load_alias_cache(session)
                unknowns = collect_unknowns(normalized_rows, alias_cache)
                unknown_counts = {alias_type: len(values) for alias_type, values in unknowns.items()}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {
        "poi_count": len(normalized_rows),
        "remaining_unknowns": unknown_counts,
        "llm_mappings_saved": saved_count,
    }


def run_phase3(file_path: Optional[str | Path] = None, sheet_name: Optional[str] = None) -> dict:
    normalized_rows = _load_normalized_rows(file_path, sheet_name)

    session = get_session()
    try:
        alias_cache = load_alias_cache(session)

        base_signal_rows = generate_deterministic_base_signals(normalized_rows, alias_cache)
        base_saved = upsert_poi_signals(session, base_signal_rows)
        session.commit()

        llm_saved = 0
        summaries_saved = 0
        if settings.llm_signal_enrichment_enabled:
            if not core_settings.OPENAI_API_KEY:
                logger.warning(
                    "LLM_SIGNAL_ENRICHMENT_ENABLED is true but OPENAI_API_KEY is not set; "
                    "skipping LiteLLM signal enrichment for %d POI(s)",
                    len(normalized_rows),
                )
            else:
                signals_by_poi: dict[str, list[dict]] = {}
                for row in base_signal_rows:
                    signals_by_poi.setdefault(row["poi_id"], []).append(row)

                intent_targets = sorted(
                    {
                        target.target_id
                        for (alias_type, _alias_norm), target in alias_cache.items()
                        if alias_type == "intent"
                    }
                )

                llm = LiteLLMService(model=core_settings.LLM_MODEL, temperature=core_settings.LLM_TEMPERATURE)
                enriched_signals, summaries = enrich_pois_with_litellm(
                    normalized_rows,
                    signals_by_poi,
                    intent_targets,
                    llm,
                    batch_size=settings.llm_signal_batch_size,
                )
                llm_saved = upsert_poi_signals(session, enriched_signals)
                summaries_saved = save_enrichment_summaries(session, summaries)
                session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {
        "poi_count": len(normalized_rows),
        "base_signals_saved": base_saved,
        "llm_signals_saved": llm_saved,
        "enrichment_summaries_saved": summaries_saved,
    }


def run_phase4() -> dict:
    session = get_session()
    try:
        pois = session.query(Poi).options(selectinload(Poi.signals)).all()

        text_updates = []
        doc_rows = []
        doc_type_counts: dict[str, int] = {}

        for poi in pois:
            semantic_text = build_semantic_text(poi, poi.signals)
            keyword_text = build_keyword_text(poi, poi.signals)
            text_updates.append(
                {"poi_id": poi.poi_id, "semantic_text": semantic_text, "keyword_text": keyword_text}
            )

            docs = build_search_documents(poi, poi.signals, semantic_text, keyword_text)
            doc_rows.extend(docs)
            for doc in docs:
                doc_type_counts[doc["doc_type"]] = doc_type_counts.get(doc["doc_type"], 0) + 1

        texts_saved = save_pois_text(session, text_updates)
        docs_saved = upsert_search_documents(session, doc_rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {
        "poi_count": len(pois),
        "pois_text_updated": texts_saved,
        "search_documents_saved": docs_saved,
        "doc_type_counts": doc_type_counts,
    }
