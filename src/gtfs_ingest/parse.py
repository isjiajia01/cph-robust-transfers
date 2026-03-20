from __future__ import annotations

import argparse
import csv
from pathlib import Path
from zipfile import ZipFile

REQUIRED_FILES = [
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
]

OPTIONAL_FILES = [
    "transfers.txt",
    "calendar.txt",
    "calendar_dates.txt",
]


def extract_csv_from_zip(zip_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        missing = [f for f in REQUIRED_FILES if f not in names]
        if missing:
            raise FileNotFoundError(f"Missing required GTFS files: {missing}")

        for filename in REQUIRED_FILES + OPTIONAL_FILES:
            if filename not in names:
                continue
            target = out_dir / filename.replace(".txt", ".csv")
            with zf.open(filename) as src, target.open("wb") as dst:
                dst.write(src.read())
            _validate_csv_header(target)
            written.append(target)

    return written


def _validate_csv_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Empty GTFS table: {path}") from exc
        if not header:
            raise ValueError(f"Missing header in GTFS table: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse GTFS zip into CSV tables")
    parser.add_argument("--input", required=True, help="Path to GTFS zip")
    parser.add_argument("--out", default="data/gtfs/parsed/latest", help="Output directory")
    args = parser.parse_args()

    written = extract_csv_from_zip(Path(args.input), Path(args.out))
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
