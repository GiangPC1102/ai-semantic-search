"""Evaluate the Tasco search API against the Track-2 Public_Evaluation set."""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import pandas as pd

logger = logging.getLogger("evaluate_tasco_search")

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_XLSX = WORKSPACE_ROOT / "data" / "ai_maps_track2_dataset_participants.xlsx"
DEFAULT_OUTPUT_XLSX = WORKSPACE_ROOT / "data" / "tasco_search_evaluation.xlsx"
DEFAULT_SHEET = "Public_Evaluation"
DEFAULT_API_BASE = os.getenv("TASCO_API_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = float(os.getenv("TASCO_API_TIMEOUT", "60"))
DEFAULT_MAX_RETRIES = int(os.getenv("TASCO_API_MAX_RETRIES", "3"))
DEFAULT_METRIC_K = int(os.getenv("TASCO_EVAL_K", "10"))
DEFAULT_IS_FILTER_ATTRIBUTE = False

SEARCH_PATH = "/tasco/search"
JOIN_SEP = ";"

GROUND_TRUTH_COLUMNS: tuple[str, ...] = (
    "query_id",
    "input_query",
    "expected_top_poi_ids",
    "expected_semantic_requirements",
    "ranking_signals_to_use",
)
OUTPUT_COLUMNS: tuple[str, ...] = GROUND_TRUTH_COLUMNS + (
    "predict_top_poi_ids",
    "predict_attribute",
    "predict_signals",
    "recall",
    "precision",
    "ndcg",
    "average_precision",
    "error",
)


def load_ground_truth(
    input_path: Path,
    sheet: str = DEFAULT_SHEET,
    columns: Sequence[str] = GROUND_TRUTH_COLUMNS,
) -> pd.DataFrame:
    """Load and project the ground-truth columns from the dataset workbook."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input workbook not found: {input_path}")
    df = pd.read_excel(input_path, sheet_name=sheet, dtype=str)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"Sheet '{sheet}' is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )
    return df[list(columns)].copy()


def call_tasco_search(
    client: httpx.Client,
    api_base: str,
    query: str,
    poi_top_k: int | None = None,
    attribute_top_k: int | None = None,
    is_filter_attribute: bool = DEFAULT_IS_FILTER_ATTRIBUTE,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Call ``POST {api_base}/tasco/search`` with exponential-backoff retries."""
    payload: dict[str, Any] = {
        "query": query,
        "is_filter_attribute": is_filter_attribute,
    }
    if poi_top_k is not None:
        payload["poi_top_k"] = poi_top_k
    if attribute_top_k is not None:
        payload["attribute_top_k"] = attribute_top_k
    url = f"{api_base.rstrip('/')}{SEARCH_PATH}"

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            backoff = min(2 ** (attempt - 1), 8)
            logger.warning(
                "Query '%s' failed (attempt %d/%d): %s — retrying in %ds",
                query, attempt, max_retries, exc, backoff,
            )
            time.sleep(backoff)
    raise last_error  # type: ignore[misc]


def _join_unique(values: Iterable[Any]) -> str:
    """Join non-null, non-empty values with ``JOIN_SEP``, preserving first-seen order."""
    texts = [
        text
        for text in (str(v).strip() for v in values if v is not None)
        if text
    ]
    return JOIN_SEP.join(dict.fromkeys(texts))


def extract_predictions(response: dict[str, Any]) -> dict[str, Any]:
    """Project the API response into the comparison columns."""
    items = response.get("items") or []
    first_explain = (items[0].get("explain") or {}) if items else {}
    return {
        "predict_top_poi_ids": _join_unique(item.get("poi_id") for item in items),
        "predict_attribute": _join_unique(
            label
            for item in items
            for label in ((item.get("explain") or {}).get("attributes") or [])
        ),
        "predict_signals": _join_unique(first_explain.get("ranking_signals") or []),
    }


def parse_id_list(text: Any, sep: str = JOIN_SEP) -> list[str]:
    """Split a separator-joined id string into a clean, ordered list."""

    if text is None or (isinstance(text, float) and pd.isna(text)):
        return []
    return [token.strip() for token in str(text).split(sep) if token.strip()]


def _format_metric(value: float | None) -> str:
    """Format a metric value for logging."""
    return f"{value:.3f}" if value is not None else "n/a"


def compute_recall_at_k(
    expected_ids: Sequence[str],
    predicted_ids: Sequence[str],
    k: int,
) -> float | None:
    """Recall@K = |relevant ∩ top-K| / |relevant|."""
    expected = list(expected_ids)
    if not expected or k <= 0:
        return None
    expected_set = set(expected)
    hits = sum(1 for poi_id in predicted_ids[:k] if poi_id in expected_set)
    return hits / len(expected)


def compute_precision_at_k(
    expected_ids: Sequence[str],
    predicted_ids: Sequence[str],
    k: int,
) -> float | None:
    """Precision@K = |relevant ∩ top-K| / K."""
    if k <= 0:
        return None
    expected_set = set(expected_ids)
    hits = sum(1 for poi_id in predicted_ids[:k] if poi_id in expected_set)
    return hits / k


def _graded_relevance(expected_ids: Sequence[str]) -> dict[str, float]:
    """Map each ground-truth id to graded relevance from its rank order.

    First item gets ``len(expected)``, last item gets ``1``.
    """
    expected = list(dict.fromkeys(expected_ids))
    n_relevant = len(expected)
    return {
        poi_id: float(n_relevant - rank)
        for rank, poi_id in enumerate(expected)
    }


def _dcg_at_k(relevances: Sequence[float], k: int) -> float:
    """Discounted Cumulative Gain at cutoff K."""
    score = 0.0
    for index, relevance in enumerate(relevances[:k]):
        if relevance <= 0:
            continue
        # rank is 1-based → discount by log2(rank + 1)
        score += relevance / math.log2(index + 2)
    return score


def compute_ndcg_at_k(
    expected_ids: Sequence[str],
    predicted_ids: Sequence[str],
    k: int,
) -> float | None:
    """nDCG@K with graded relevance from ground-truth order."""
    if k <= 0:
        return None
    relevance_by_id = _graded_relevance(expected_ids)
    if not relevance_by_id:
        return None

    predicted_relevances = [
        relevance_by_id.get(poi_id, 0.0) for poi_id in predicted_ids[:k]
    ]
    ideal_relevances = sorted(relevance_by_id.values(), reverse=True)
    ideal_dcg = _dcg_at_k(ideal_relevances, k)
    if ideal_dcg <= 0:
        return None
    return _dcg_at_k(predicted_relevances, k) / ideal_dcg


def compute_average_precision_at_k(
    expected_ids: Sequence[str],
    predicted_ids: Sequence[str],
    k: int,
) -> float | None:
    """Average Precision@K (AP@K).

    ``AP@K = (1 / min(|relevant|, K)) * Σ Precision@i · rel(i)`` for i ≤ K.
    MAP is the mean of AP across queries (see ``summarize``).
    """
    expected = list(dict.fromkeys(expected_ids))
    if not expected or k <= 0:
        return None

    expected_set = set(expected)
    hit_count = 0
    precision_sum = 0.0
    for index, poi_id in enumerate(predicted_ids[:k], start=1):
        if poi_id not in expected_set:
            continue
        hit_count += 1
        precision_sum += hit_count / index

    if hit_count == 0:
        return 0.0

    denominator = min(len(expected), k)
    return precision_sum / denominator


def compute_metrics(
    expected_ids: Sequence[str],
    predicted_ids: Sequence[str],
    k: int,
) -> dict[str, float | None]:
    """Compute recall@K, precision@K, nDCG@K, and AP@K for one query."""
    return {
        "recall": compute_recall_at_k(expected_ids, predicted_ids, k),
        "precision": compute_precision_at_k(expected_ids, predicted_ids, k),
        "ndcg": compute_ndcg_at_k(expected_ids, predicted_ids, k),
        "average_precision": compute_average_precision_at_k(
            expected_ids, predicted_ids, k
        ),
    }


def log_query_result(
    query_id: Any,
    metrics: dict[str, float | None],
    error: str,
    k: int,
) -> None:
    """Emit a single-line per-query metrics summary."""
    summary = (
        f"recall@{k}={_format_metric(metrics.get('recall'))} "
        f"precision@{k}={_format_metric(metrics.get('precision'))} "
        f"ndcg@{k}={_format_metric(metrics.get('ndcg'))} "
        f"ap@{k}={_format_metric(metrics.get('average_precision'))}"
    )
    if error:
        logger.info("query_id=%s %s (FAILED: %s)", query_id, summary, error)
        return
    logger.info("query_id=%s %s", query_id, summary)


def summarize(results: pd.DataFrame) -> dict[str, float]:
    """Aggregate ranking metrics across evaluated queries (``None`` excluded)."""
    def _mean(column: str) -> float:
        valid = results[results[column].notna()]
        return float(valid[column].mean()) if len(valid) else 0.0

    return {
        "total": len(results),
        "failed": int(results["error"].astype(bool).sum()),
        "mean_recall": _mean("recall"),
        "mean_precision": _mean("precision"),
        "mean_ndcg": _mean("ndcg"),
        "map": _mean("average_precision"),
    }


def evaluate(
    ground_truth: pd.DataFrame,
    api_base: str,
    poi_top_k: int | None = None,
    attribute_top_k: int | None = None,
    is_filter_attribute: bool = DEFAULT_IS_FILTER_ATTRIBUTE,
    metric_k: int = DEFAULT_METRIC_K,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> pd.DataFrame:
    """Run the API for every row, compute ranking metrics, and log results."""

    rows: list[dict[str, Any]] = []
    total = len(ground_truth)

    with httpx.Client() as client:
        for index, row in ground_truth.iterrows():
            query_id = row.get("query_id")
            query = row.get("input_query")
            logger.info("[%d/%d] query_id=%s -> '%s'", index + 1, total, query_id, query)

            record: dict[str, Any] = {col: row.get(col) for col in GROUND_TRUTH_COLUMNS}
            record.update(
                {
                    "predict_top_poi_ids": "",
                    "predict_attribute": "",
                    "predict_signals": "",
                    "recall": None,
                    "precision": None,
                    "ndcg": None,
                    "average_precision": None,
                    "error": "",
                }
            )

            if not query or not str(query).strip():
                record["error"] = "empty input_query"
            else:
                try:
                    response = call_tasco_search(
                        client=client,
                        api_base=api_base,
                        query=str(query),
                        poi_top_k=poi_top_k,
                        attribute_top_k=attribute_top_k,
                        is_filter_attribute=is_filter_attribute,
                        timeout=timeout,
                        max_retries=max_retries,
                    )
                    record.update(extract_predictions(response))
                except Exception as exc:  # noqa: BLE001 — keep evaluating the rest
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    logger.error("query_id=%s failed: %s", query_id, exc)

            metrics = compute_metrics(
                expected_ids=parse_id_list(row.get("expected_top_poi_ids")),
                predicted_ids=parse_id_list(record["predict_top_poi_ids"]),
                k=metric_k,
            )
            record.update(metrics)
            log_query_result(query_id, metrics, record.get("error", ""), metric_k)
            rows.append(record)

    return pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))


def save_results(results: pd.DataFrame, output_path: Path) -> None:
    """Persist the comparison DataFrame to an Excel file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.drop(columns=["error"]).to_excel(
        output_path, index=False, sheet_name="Evaluation"
    )
    logger.info("Wrote %d rows to %s", len(results), output_path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments with sensible defaults from constants/env."""
    parser = argparse.ArgumentParser(
        description="Evaluate /tasco/search against the Public_Evaluation sheet.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_XLSX,
                        help=f"Dataset .xlsx path (default: {DEFAULT_INPUT_XLSX})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_XLSX,
                        help=f"Output .xlsx path (default: {DEFAULT_OUTPUT_XLSX})")
    parser.add_argument("--sheet", default=DEFAULT_SHEET,
                        help=f"Sheet name to read (default: {DEFAULT_SHEET})")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE,
                        help=f"Tasco API base URL (default: {DEFAULT_API_BASE})")
    parser.add_argument(
        "--poi-top-k",
        type=int,
        default=None,
        help="Override POI vector search top_k (default: API default).",
    )
    parser.add_argument("--attribute-top-k", type=int, default=None,
                        help="Override attribute vector search top_k (default: API default).")
    parser.add_argument(
        "--is-filter-attribute",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_IS_FILTER_ATTRIBUTE,
        help=(
            "Enable attribute search + intersect "
            f"(default: {DEFAULT_IS_FILTER_ATTRIBUTE}). "
            "Use --no-is-filter-attribute to disable."
        ),
    )
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_METRIC_K,
        help=(
            "Cutoff K for recall@K, precision@K, nDCG@K, and AP@K "
            f"(default: {DEFAULT_METRIC_K})."
        ),
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                        help=f"Max attempts per query on transient errors (default: {DEFAULT_MAX_RETRIES})")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging verbosity (default: INFO)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.k <= 0:
        logger.error("--k must be a positive integer, got %s", args.k)
        return 2

    try:
        ground_truth = load_ground_truth(args.input, sheet=args.sheet)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Failed to load ground truth: %s", exc)
        return 2

    logger.info(
        "Loaded %d queries from '%s' (sheet='%s'), metric_k=%d, "
        "poi_top_k=%s, is_filter_attribute=%s",
        len(ground_truth),
        args.input,
        args.sheet,
        args.k,
        args.poi_top_k,
        args.is_filter_attribute,
    )

    results = evaluate(
        ground_truth=ground_truth,
        api_base=args.api_base,
        poi_top_k=args.poi_top_k,
        attribute_top_k=args.attribute_top_k,
        is_filter_attribute=args.is_filter_attribute,
        metric_k=args.k,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    summary = summarize(results)
    logger.info(
        "Summary: total=%d failed=%d "
        "mean_recall@%d=%.3f mean_precision@%d=%.3f "
        "mean_ndcg@%d=%.3f MAP@%d=%.3f",
        summary["total"],
        summary["failed"],
        args.k,
        summary["mean_recall"],
        args.k,
        summary["mean_precision"],
        args.k,
        summary["mean_ndcg"],
        args.k,
        summary["map"],
    )

    save_results(results, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
