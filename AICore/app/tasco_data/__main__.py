import argparse
import logging

from app.tasco_data.pipeline import run_phase1, run_phase2, run_phase3, run_phase4


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline POI ingestion pipeline.")
    parser.add_argument("file_path", nargs="?", default=None, help="Path to the POI dataset .xlsx file")
    parser.add_argument("--sheet", default=None, help="Sheet name to read (default: POI_Dataset)")
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        help=(
            "Pipeline phase to run: 1=ingest POIs, 2=dynamic taxonomy normalization, "
            "3=signals and enrichment, 4=search documents"
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.phase == 1:
        count = run_phase1(file_path=args.file_path, sheet_name=args.sheet)
        print(f"Upserted {count} POIs into Postgres")
    elif args.phase == 2:
        result = run_phase2(file_path=args.file_path, sheet_name=args.sheet)
        print(f"Phase 2 result: {result}")
    elif args.phase == 3:
        result = run_phase3(file_path=args.file_path, sheet_name=args.sheet)
        print(f"Phase 3 result: {result}")
    else:
        result = run_phase4()
        print(f"Phase 4 result: {result}")


if __name__ == "__main__":
    main()
