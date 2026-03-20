from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from src.robustness.risk_model import ModeLevelRiskModel, RiskModel


@dataclass(frozen=True)
class RouterConfig:
    slack_min: float = 6.0
    minimum_transfer_time_min: float = 3.0
    walk_time_assumption_min: float = 2.0
    missed_transfer_rule: str = "p90_delay_vs_effective_slack"


def _load_router_config(path: Path) -> RouterConfig:
    if tomllib is None:
        raise RuntimeError("tomllib is required to load router config")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    section = raw.get("router", {})
    return RouterConfig(
        slack_min=float(section.get("slack_min", 6.0)),
        minimum_transfer_time_min=float(section.get("minimum_transfer_time_min", 3.0)),
        walk_time_assumption_min=float(section.get("walk_time_assumption_min", 2.0)),
        missed_transfer_rule=str(section.get("missed_transfer_rule", "p90_delay_vs_effective_slack")),
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _parse_depart_ts(hour_value: str) -> int:
    try:
        dt = datetime.fromisoformat(hour_value.replace("Z", "+00:00"))
        return dt.hour
    except ValueError:
        return 0


def _miss_prob(p90_delay_sec: int, slack_min: float, min_transfer_min: float) -> float:
    slack_sec = max(0.0, (slack_min - min_transfer_min) * 60.0)
    if slack_sec <= 0:
        return 1.0
    ratio = max(0.0, min(3.0, p90_delay_sec / slack_sec))
    return round(min(0.99, 0.2 * ratio + 0.15 * (ratio**2)), 6)


def _cvar95_min(p95_delay_sec: int, walk_min: float) -> float:
    return round((max(0, p95_delay_sec) / 60.0) + walk_min, 4)


def _build_context(candidate: dict[str, str], hour_cph: int) -> dict[str, Any]:
    return {
        "od_id": candidate.get("od_id", ""),
        "path_id": candidate.get("path_id", ""),
        "depart_ts_cph": candidate.get("depart_ts_cph", ""),
        "hour_cph": hour_cph,
        "stop_type": candidate.get("stop_type", ""),
    }


def run_router(
    candidates: list[dict[str, str]],
    model: RiskModel,
    config: RouterConfig,
) -> list[dict]:
    out: list[dict] = []
    for c in candidates:
        line = (c.get("line") or "UNKNOWN").strip() or "UNKNOWN"
        mode = (c.get("mode") or "UNKNOWN").strip() or "UNKNOWN"
        stop_type = (c.get("stop_type") or "").strip()
        hour_cph = _parse_depart_ts(c.get("depart_ts_cph", ""))
        context = _build_context(c, hour_cph)
        est = model.estimate(line=line, mode=mode, hour_cph=hour_cph, stop_type=stop_type, context=context)
        travel_time_min = float(c.get("travel_time_min") or 0.0)
        transfers = int(float(c.get("transfers") or 0))
        miss_prob = _miss_prob(
            est.p90_delay_sec,
            slack_min=config.slack_min,
            min_transfer_min=config.minimum_transfer_time_min,
        )
        out.append(
            {
                "od_id": c.get("od_id", ""),
                "depart_ts_cph": c.get("depart_ts_cph", ""),
                "path_id": c.get("path_id", ""),
                "travel_time_min": round(travel_time_min, 4),
                "transfers": transfers,
                "miss_prob": miss_prob,
                "cvar95_min": _cvar95_min(est.p95_delay_sec, walk_min=config.walk_time_assumption_min),
                "p50_delay_sec": est.p50_delay_sec,
                "p90_delay_sec": est.p90_delay_sec,
                "p95_delay_sec": est.p95_delay_sec,
                "p50_ci_low": est.p50_ci_low,
                "p50_ci_high": est.p50_ci_high,
                "p90_ci_low": est.p90_ci_low,
                "p90_ci_high": est.p90_ci_high,
                "p95_ci_low": est.p95_ci_low,
                "p95_ci_high": est.p95_ci_high,
                "evidence_level": est.evidence_level,
                "sample_size_effective": est.sample_size_effective,
                "risk_model_version": est.risk_model_version,
                "confidence_tag": est.confidence_tag,
                "ci95_width_sec": est.ci95_width_sec,
                "hour_cph": hour_cph,
                "stop_type": stop_type,
                "source_level": est.source_level,
                "delay_distribution": est.delay_distribution,
                "router_config_version": config.missed_transfer_rule,
                "context_json": json.dumps(context, ensure_ascii=True, sort_keys=True),
                "uncertainty_note": est.uncertainty_note,
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate robust transfer candidates and emit Pareto-ready table")
    parser.add_argument("--departures", required=True, help="departures.csv for risk model fitting")
    parser.add_argument("--candidates", required=True, help="candidate paths csv")
    parser.add_argument("--out", default="data/analysis/router_pareto_table.csv")
    parser.add_argument("--config", default="configs/router.defaults.toml")
    parser.add_argument("--slack-min", type=float, default=6.0)
    parser.add_argument("--min-transfer-min", type=float, default=3.0)
    parser.add_argument("--walk-min", type=float, default=2.0)
    parser.add_argument("--n-mode-hour-min", type=int, default=200)
    parser.add_argument("--n-line-min", type=int, default=None, help="Deprecated alias for --n-mode-hour-min")
    parser.add_argument("--n-mode-min", type=int, default=500)
    parser.add_argument("--bootstrap-iters", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    departures = _read_rows(Path(args.departures))
    candidates = _read_rows(Path(args.candidates))
    n_mode_hour_min = args.n_mode_hour_min if args.n_line_min is None else args.n_line_min
    model = ModeLevelRiskModel(
        departures,
        n_mode_hour_min=n_mode_hour_min,
        n_mode_min=args.n_mode_min,
        bootstrap_iters=args.bootstrap_iters,
        seed=args.seed,
    )
    config_path = Path(args.config)
    if config_path.exists():
        config = _load_router_config(config_path)
    else:
        config = RouterConfig(
            slack_min=args.slack_min,
            minimum_transfer_time_min=args.min_transfer_min,
            walk_time_assumption_min=args.walk_min,
        )
    out_rows = run_router(
        candidates,
        model,
        config=config,
    )
    _write_rows(
        Path(args.out),
        out_rows,
        [
            "od_id",
            "depart_ts_cph",
            "path_id",
            "travel_time_min",
            "transfers",
            "miss_prob",
            "cvar95_min",
            "p50_delay_sec",
            "p90_delay_sec",
            "p95_delay_sec",
            "p50_ci_low",
            "p50_ci_high",
            "p90_ci_low",
            "p90_ci_high",
            "p95_ci_low",
            "p95_ci_high",
            "evidence_level",
            "sample_size_effective",
            "risk_model_version",
            "confidence_tag",
            "ci95_width_sec",
            "hour_cph",
            "stop_type",
            "source_level",
            "delay_distribution",
            "router_config_version",
            "context_json",
            "uncertainty_note",
        ],
    )
    print(args.out)


if __name__ == "__main__":
    main()
