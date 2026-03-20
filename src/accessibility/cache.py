from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.common.io import ensure_parent


@dataclass(frozen=True)
class ReachabilityQuery:
    origin_key: str
    depart_at_local: str
    max_minutes: int
    modes: tuple[str, ...]
    max_changes: int


@dataclass(frozen=True)
class CacheResult:
    payload: dict[str, object]
    hit: bool
    source: str
    stale: bool
    age_sec: int


def normalize_modes(modes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(mode.strip().lower() for mode in modes if mode and mode.strip()))


def bucket_time_local(iso_local_ts: str, bucket_minutes: int = 5) -> tuple[str, str]:
    dt = datetime.fromisoformat(iso_local_ts)
    floored_minute = dt.minute - (dt.minute % bucket_minutes)
    bucket_dt = dt.replace(minute=floored_minute, second=0, microsecond=0)
    return bucket_dt.date().isoformat(), bucket_dt.strftime("%Y-%m-%dT%H:%M")


def build_location_search_cache_key(query: str, limit: int, version: str = "v1") -> str:
    normalized = " ".join(query.lower().strip().split())
    return f"location:{version}:{normalized}:{limit}"


def build_reachability_cache_key(
    query: ReachabilityQuery,
    bucket_minutes: int = 5,
    version: str = "v1",
) -> str:
    service_date_local, time_bucket_local = bucket_time_local(query.depart_at_local, bucket_minutes=bucket_minutes)
    modes = ",".join(normalize_modes(query.modes))
    return (
        f"reachability:{version}:"
        f"origin={query.origin_key}:"
        f"date={service_date_local}:"
        f"time={time_bucket_local}:"
        f"dur={int(query.max_minutes)}:"
        f"modes={modes}:"
        f"changes={int(query.max_changes)}"
    )


def build_cache_path(cache_root: Path, cache_key: str) -> Path:
    safe_name = cache_key.replace(":", "__").replace("/", "_")
    return cache_root / f"{safe_name}.json"


def _now_epoch() -> float:
    return time.time()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JsonCache:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root
        self._memory: dict[str, tuple[float, dict[str, object]]] = {}

    def get(self, cache_key: str, ttl_sec: int, *, allow_stale: bool = False) -> CacheResult | None:
        now = _now_epoch()
        hit = self._memory.get(cache_key)
        if hit is not None:
            saved_at, payload = hit
            age_sec = int(max(0, now - saved_at))
            stale = age_sec > ttl_sec
            if allow_stale or not stale:
                return CacheResult(payload=payload, hit=True, source="memory", stale=stale, age_sec=age_sec)

        disk_path = build_cache_path(self.cache_root, cache_key)
        if not disk_path.exists():
            return None

        try:
            raw = json.loads(disk_path.read_text(encoding="utf-8"))
            saved_at = float(raw["saved_at_epoch"])
            payload = raw["payload"]
        except Exception:
            return None

        self._memory[cache_key] = (saved_at, payload)
        age_sec = int(max(0, now - saved_at))
        stale = age_sec > ttl_sec
        if allow_stale or not stale:
            return CacheResult(payload=payload, hit=True, source="disk", stale=stale, age_sec=age_sec)
        return None

    def set(self, cache_key: str, payload: dict[str, object]) -> None:
        saved_at = _now_epoch()
        self._memory[cache_key] = (saved_at, payload)
        disk_path = build_cache_path(self.cache_root, cache_key)
        ensure_parent(disk_path)
        disk_path.write_text(
            json.dumps(
                {
                    "saved_at_epoch": saved_at,
                    "saved_at_utc": _utc_now_iso(),
                    "payload": payload,
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )
