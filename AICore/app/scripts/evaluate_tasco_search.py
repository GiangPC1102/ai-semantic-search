"""Evaluate the Tasco search API against the Track-2 Public_Evaluation set."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import pandas as pd
from sklearn.metrics import recall_score
from sklearn.preprocessing import MultiLabelBinarizer

logger = logging.getLogger("evaluate_tasco_search")

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_XLSX = WORKSPACE_ROOT / "data" / "ai_maps_track2_dataset_participants.xlsx"
DEFAULT_OUTPUT_XLSX = WORKSPACE_ROOT / "data" / "tasco_search_evaluation.xlsx"
DEFAULT_SHEET = "Public_Evaluation"
DEFAULT_API_BASE = os.getenv("TASCO_API_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = float(os.getenv("TASCO_API_TIMEOUT", "60"))
DEFAULT_MAX_RETRIES = int(os.getenv("TASCO_API_MAX_RETRIES", "3"))

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
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Call ``POST {api_base}/tasco/search`` with exponential-backoff retries."""
    payload: dict[str, Any] = {"query": query}
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
    return {
        "predict_top_poi_ids": _join_unique(item.get("poi_id") for item in items),
        "predict_attribute": _join_unique(
            hit.get("name") for hit in (response.get("attribute_hits") or [])
        ),
        "predict_signals": _join_unique(
            signal.get("signal") for signal in (response.get("ranking_signals") or [])
        ),
    }


def parse_id_list(text: Any, sep: str = JOIN_SEP) -> list[str]:
    """Split a separator-joined id string into a clean, ordered list."""

    if text is None or (isinstance(text, float) and pd.isna(text)):
        return []
    return [token.strip() for token in str(text).split(sep) if token.strip()]


def compute_recall(
    expected_ids: Sequence[str], predicted_ids: Sequence[str]
) -> float | None:
    """Compute recall@k."""

    expected = list(expected_ids)
    if not expected:
        return None
    binariser = MultiLabelBinarizer()
    y_true = binariser.fit_transform([expected])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y_pred = binariser.transform([list(predicted_ids)])
        return float(
            recall_score(y_true, y_pred, average="micro", zero_division=0)
        )


def log_query_result(query_id: Any, recall: float | None, error: str) -> None:
    """Emit a single-line per-query recall summary."""
    recall_str = f"{recall:.3f}" if recall is not None else "n/a"
    if error:
        logger.info("query_id=%s recall=%s (FAILED: %s)", query_id, recall_str, error)
        return
    logger.info("query_id=%s recall=%s", query_id, recall_str)


def summarize(results: pd.DataFrame) -> dict[str, float]:
    """Aggregate recall across all evaluated queries (``None`` recall excluded)."""
    valid = results[results["recall"].notna()]
    return {
        "total": len(results),
        "failed": int(results["error"].astype(bool).sum()),
        "mean_recall": float(valid["recall"].mean()) if len(valid) else 0.0,
    }


def evaluate(
    ground_truth: pd.DataFrame,
    api_base: str,
    poi_top_k: int | None = None,
    attribute_top_k: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> pd.DataFrame:
    """Run the API for every row, compute recall per query, and log results."""

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
                        timeout=timeout,
                        max_retries=max_retries,
                    )
                    record.update(extract_predictions(response))
                except Exception as exc:  # noqa: BLE001 — keep evaluating the rest
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    logger.error("query_id=%s failed: %s", query_id, exc)

            record["recall"] = compute_recall(
                expected_ids=parse_id_list(row.get("expected_top_poi_ids")),
                predicted_ids=parse_id_list(record["predict_top_poi_ids"]),
            )
            log_query_result(query_id, record["recall"], record.get("error", ""))
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
    parser.add_argument("--poi-top-k", type=int, default=None,
                        help="Override POI vector search top_k (default: API default).")
    parser.add_argument("--attribute-top-k", type=int, default=None,
                        help="Override attribute vector search top_k (default: API default).")
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

    try:
        ground_truth = load_ground_truth(args.input, sheet=args.sheet)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Failed to load ground truth: %s", exc)
        return 2

    logger.info(
        "Loaded %d queries from '%s' (sheet='%s')",
        len(ground_truth), args.input, args.sheet,
    )

    results = evaluate(
        ground_truth=ground_truth,
        api_base=args.api_base,
        poi_top_k=args.poi_top_k,
        attribute_top_k=args.attribute_top_k,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    summary = summarize(results)
    logger.info(
        "Summary: total=%d failed=%d mean_recall=%.3f",
        summary["total"], summary["failed"], summary["mean_recall"],
    )

    save_results(results, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
