from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def download_gtfs(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"gtfs_{stamp}.zip"

    with urlopen(url) as response, out_path.open("wb") as f:
        f.write(response.read())

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download GTFS zip")
    parser.add_argument("--url", required=True, help="GTFS static ZIP URL")
    parser.add_argument("--out-dir", default="data/gtfs/raw", help="Output directory")
    args = parser.parse_args()

    path = download_gtfs(args.url, Path(args.out_dir))
    print(path)


if __name__ == "__main__":
    main()
