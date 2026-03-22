from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.accessibility.cache import ReachabilityQuery, normalize_modes


@dataclass(frozen=True)
class OriginRef:
    id: str = ""
    type: str = "stop"
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class RejseplanenAPIConfig:
    base_url: str
    request_timeout_sec: int
    location_search_limit: int
    max_minutes_default: int
    max_changes_default: int
    access_id_env: str
    access_id_query_param: str
    format_param: str
    format_value: str
    location_search_path: str
    location_search_query_param: str
    location_search_limit_param: str
    reachability_path: str
    reachability_origin_id_param: str
    reachability_origin_lat_param: str
    reachability_origin_lon_param: str
    reachability_date_param: str
    reachability_time_param: str
    reachability_duration_param: str
    reachability_max_changes_param: str
    reachability_forward_param: str
    reachability_forward_default: int
    reachability_filter_end_walks_param: str
    reachability_filter_end_walks_default: int
    reachability_modes_param: str
    mode_separator: str


@dataclass(frozen=True)
class RejseplanenResponse:
    request_url: str
    raw_payload: dict[str, object]
    normalized_items: list[dict[str, object]]


def build_location_search_params(
    query: str,
    limit: int,
    api_cfg: RejseplanenAPIConfig,
    access_id: str,
) -> dict[str, str]:
    return {
        api_cfg.location_search_query_param: query.strip(),
        api_cfg.location_search_limit_param: str(limit),
        api_cfg.access_id_query_param: access_id,
        api_cfg.format_param: api_cfg.format_value,
    }


def build_reachability_params(
    origin: OriginRef,
    query: ReachabilityQuery,
    api_cfg: RejseplanenAPIConfig,
    access_id: str,
) -> dict[str, str]:
    dt = datetime.fromisoformat(query.depart_at_local)
    params = {
        api_cfg.access_id_query_param: access_id,
        api_cfg.format_param: api_cfg.format_value,
        api_cfg.reachability_date_param: dt.date().isoformat(),
        api_cfg.reachability_time_param: dt.strftime("%H:%M"),
        api_cfg.reachability_duration_param: str(int(query.max_minutes)),
        api_cfg.reachability_max_changes_param: str(int(query.max_changes)),
    }
    if api_cfg.reachability_forward_param:
        params[api_cfg.reachability_forward_param] = str(int(api_cfg.reachability_forward_default))
    if api_cfg.reachability_filter_end_walks_param:
        params[api_cfg.reachability_filter_end_walks_param] = str(int(api_cfg.reachability_filter_end_walks_default))
    if origin.id:
        params[api_cfg.reachability_origin_id_param] = origin.id
    if origin.lat is not None and origin.lon is not None:
        params[api_cfg.reachability_origin_lat_param] = f"{origin.lat:.6f}"
        params[api_cfg.reachability_origin_lon_param] = f"{origin.lon:.6f}"
    if api_cfg.reachability_modes_param and query.modes:
        normalized_modes = normalize_modes(query.modes)
        if api_cfg.reachability_modes_param == "products":
            products = _products_mask_for_modes(normalized_modes)
            if products > 0:
                params[api_cfg.reachability_modes_param] = str(products)
        else:
            params[api_cfg.reachability_modes_param] = api_cfg.mode_separator.join(normalized_modes)
    return params


def _products_mask_for_modes(modes: tuple[str, ...]) -> int:
    mask = 0
    for mode in modes:
        if mode == "train":
            mask |= 1 | 2 | 4 | 8 | 16
        elif mode == "bus":
            mask |= 32 | 64
        elif mode == "metro":
            mask |= 1024
    return mask


def _json_request(url: str, timeout_sec: int) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Rejseplanen HTTP {exc.code}: {detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Rejseplanen network error: {exc.reason}") from exc

    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Rejseplanen response was not valid JSON") from exc


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extract_location_id(item: dict[str, object]) -> str | None:
    for key in ("extId", "stopId", "stopid", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            found = value.strip()
            if found.startswith("A=") and "@L=" in found:
                segment = found.split("@L=", 1)[1]
                ext_id = segment.split("@", 1)[0]
                return ext_id or found
            return found
    return None


def _extract_name(item: dict[str, object]) -> str:
    for key in ("name", "label", "stop", "stopName"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_product_label(line: str, mode: str) -> tuple[str, str]:
    normalized_line = line.strip()
    normalized_mode = mode.strip()
    lowered = normalized_line.lower()
    if lowered in {"-fußweg-", "-fussweg-", "fußweg", "fussweg"}:
        return ("Walk link", "Walk")
    if normalized_mode.lower() in {"gang", "walk"} and not normalized_line:
        return ("Walk link", "Walk")
    return (normalized_line, normalized_mode)


def _extract_primary_product(item: dict[str, object]) -> tuple[str, str]:
    products = item.get("productAtStop")
    if isinstance(products, list) and products:
        first = products[0]
        if isinstance(first, dict):
            line = str(first.get("line") or first.get("name") or "").strip()
            mode = str(first.get("catOutL") or first.get("catOut") or "").strip()
            return _normalize_product_label(line, mode)
    return "", ""


def _extract_coord_pair(item: dict[str, object]) -> tuple[float | None, float | None]:
    lat_candidates = ("lat", "latitude", "y")
    lon_candidates = ("lon", "longitude", "x")
    lat = next((_as_float(item.get(key)) for key in lat_candidates if item.get(key) is not None), None)
    lon = next((_as_float(item.get(key)) for key in lon_candidates if item.get(key) is not None), None)
    if lat is None or lon is None:
        coord = item.get("coord")
        if isinstance(coord, dict):
            lat = lat if lat is not None else _as_float(coord.get("lat"))
            lon = lon if lon is not None else _as_float(coord.get("lon"))
    return lat, lon


def _iter_candidate_dicts(payload: object) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    if isinstance(payload, dict):
        candidates.append(payload)
        for value in payload.values():
            candidates.extend(_iter_candidate_dicts(value))
    elif isinstance(payload, list):
        for value in payload:
            candidates.extend(_iter_candidate_dicts(value))
    return candidates


def _normalize_location_candidates(payload: dict[str, object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in _iter_candidate_dicts(payload):
        location_id = _extract_location_id(item)
        name = _extract_name(item)
        lat, lon = _extract_coord_pair(item)
        if not location_id or not name:
            continue
        if location_id in seen:
            continue
        seen.add(location_id)
        out.append(
            {
                "id": location_id,
                "name": name,
                "type": str(item.get("type", "stop")),
                "lat": lat,
                "lon": lon,
            }
        )
    return out


def _extract_travel_time_minutes(item: dict[str, object]) -> int | None:
    direct_keys = (
        "travelTime",
        "travelTimeMin",
        "duration",
        "durationMin",
        "minutes",
        "time",
    )
    for key in direct_keys:
        value = item.get(key)
        if value is None:
            continue
        try:
            return int(float(str(value)))
        except ValueError:
            continue
    notes = item.get("LocationNotes")
    if isinstance(notes, dict):
        note_list = notes.get("LocationNote")
        if isinstance(note_list, list):
            for note in note_list:
                if isinstance(note, dict) and note.get("key") == "DURATION":
                    value = note.get("value")
                    if value is not None:
                        try:
                            return int(float(str(value)))
                        except ValueError:
                            return None
    return None


def _extract_changes(item: dict[str, object]) -> int | None:
    notes = item.get("LocationNotes")
    if isinstance(notes, dict):
        note_list = notes.get("LocationNote")
        if isinstance(note_list, list):
            for note in note_list:
                if isinstance(note, dict) and note.get("key") == "CHANGES":
                    value = note.get("value")
                    if value is not None:
                        try:
                            return int(float(str(value)))
                        except ValueError:
                            return None
    return None


def _normalize_reachability_candidates(payload: dict[str, object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in _iter_candidate_dicts(payload):
        location_id = _extract_location_id(item)
        name = _extract_name(item)
        lat, lon = _extract_coord_pair(item)
        travel_time = _extract_travel_time_minutes(item)
        if not location_id or not name or lat is None or lon is None:
            continue
        if travel_time is None:
            continue
        if location_id in seen:
            continue
        seen.add(location_id)
        line, mode = _extract_primary_product(item)
        out.append(
            {
                "id": location_id,
                "name": name,
                "lat": lat,
                "lon": lon,
                "travel_time_min": travel_time,
                "changes": _extract_changes(item),
                "raw_type": str(item.get("type", "stop")),
                "line": line,
                "mode": mode,
            }
        )
    out.sort(key=lambda row: (int(row["travel_time_min"]), row["name"]))
    return out


class RejseplanenClient:
    def __init__(self, api_cfg: RejseplanenAPIConfig) -> None:
        self.api_cfg = api_cfg

    def _access_id(self) -> str:
        value = os.getenv(self.api_cfg.access_id_env, "").strip()
        if not value:
            raise RuntimeError(
                f"Missing Rejseplanen API key in environment variable {self.api_cfg.access_id_env}"
            )
        return value

    def location_search(self, query: str, limit: int | None = None) -> RejseplanenResponse:
        access_id = self._access_id()
        request_limit = self.api_cfg.location_search_limit if limit is None else limit
        params = build_location_search_params(query=query, limit=request_limit, api_cfg=self.api_cfg, access_id=access_id)
        url = f"{self.api_cfg.base_url.rstrip('/')}/{self.api_cfg.location_search_path.lstrip('/')}?{urlencode(params)}"
        payload = _json_request(url, timeout_sec=self.api_cfg.request_timeout_sec)
        return RejseplanenResponse(
            request_url=url,
            raw_payload=payload,
            normalized_items=_normalize_location_candidates(payload),
        )

    def reachability_search(self, origin: OriginRef, query: ReachabilityQuery) -> RejseplanenResponse:
        access_id = self._access_id()
        params = build_reachability_params(origin=origin, query=query, api_cfg=self.api_cfg, access_id=access_id)
        url = f"{self.api_cfg.base_url.rstrip('/')}/{self.api_cfg.reachability_path.lstrip('/')}?{urlencode(params)}"
        payload = _json_request(url, timeout_sec=self.api_cfg.request_timeout_sec)
        return RejseplanenResponse(
            request_url=url,
            raw_payload=payload,
            normalized_items=_normalize_reachability_candidates(payload),
        )
