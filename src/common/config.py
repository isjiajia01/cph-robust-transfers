from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class SamplingConfig:
    interval_sec: int
    station_batch_size: int
    max_journey_detail_per_cycle: int


@dataclass(frozen=True)
class HttpConfig:
    timeout_sec: int
    max_retries: int
    backoff_base_sec: float
    backoff_max_sec: float


@dataclass(frozen=True)
class StorageConfig:
    raw_dir: str
    structured_dir: str


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    sampling: SamplingConfig
    http: HttpConfig
    storage: StorageConfig


def load_config(path: str | Path) -> AppConfig:
    cfg_path = Path(path)
    raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))

    return AppConfig(
        timezone=raw.get("timezone", "Europe/Copenhagen"),
        sampling=SamplingConfig(
            interval_sec=int(raw["sampling"]["interval_sec"]),
            station_batch_size=int(raw["sampling"]["station_batch_size"]),
            max_journey_detail_per_cycle=int(raw["sampling"]["max_journey_detail_per_cycle"]),
        ),
        http=HttpConfig(
            timeout_sec=int(raw["http"]["timeout_sec"]),
            max_retries=int(raw["http"]["max_retries"]),
            backoff_base_sec=float(raw["http"].get("backoff_base_sec", 1.5)),
            backoff_max_sec=float(raw["http"].get("backoff_max_sec", 60.0)),
        ),
        storage=StorageConfig(
            raw_dir=str(raw["storage"]["raw_dir"]),
            structured_dir=str(raw["storage"]["structured_dir"]),
        ),
    )
