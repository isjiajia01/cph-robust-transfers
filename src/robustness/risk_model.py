from __future__ import annotations

import argparse
import csv
import json
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class RiskModel(ABC):
    @abstractmethod
    def estimate(
        self,
        *,
        line: str,
        mode: str,
        hour_cph: int | None = None,
        stop_type: str = "",
        context: dict | None = None,
    ) -> "RiskEstimate":
        raise NotImplementedError


@dataclass(frozen=True)
class RiskEstimate:
    delay_distribution: str
    p50_delay_sec: int
    p90_delay_sec: int
    p95_delay_sec: int
    p50_ci_low: int
    p50_ci_high: int
    p90_ci_low: int
    p90_ci_high: int
    p95_ci_low: int
    p95_ci_high: int
    sample_size_effective: int
    confidence_tag: str
    evidence_level: str
    source_level: str
    ci95_width_sec: int
    risk_model_version: str
    hour_cph: int | None
    stop_type: str
    context_json: str
    shrinkage_parent_level: str
    shrinkage_weight: float
    uncertainty_note: str


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _percentile(vals: list[int], p: float) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    idx = int(round((p / 100.0) * (len(s) - 1)))
    idx = max(0, min(len(s) - 1, idx))
    return s[idx]


def _bootstrap_ci(vals: list[int], p: float, n_boot: int, seed: int) -> tuple[int, int]:
    if not vals:
        return (0, 0)
    rnd = random.Random(seed)
    qs: list[int] = []
    for _ in range(n_boot):
        sample = [vals[rnd.randrange(len(vals))] for _ in range(len(vals))]
        qs.append(_percentile(sample, p))
    qs.sort()
    lo = qs[max(0, int(0.025 * (len(qs) - 1)))]
    hi = qs[min(len(qs) - 1, int(0.975 * (len(qs) - 1)))]
    return (lo, hi)


class ModeLevelRiskModel(RiskModel):
    def __init__(
        self,
        rows: list[dict[str, str]],
        n_mode_hour_min: int = 200,
        n_mode_min: int = 500,
        bootstrap_iters: int = 1000,
        seed: int = 42,
        n_line_min: int | None = None,
    ) -> None:
        if n_line_min is not None:
            n_mode_hour_min = n_line_min
        self.n_mode_hour_min = n_mode_hour_min
        self.n_mode_min = n_mode_min
        self.bootstrap_iters = bootstrap_iters
        self.seed = seed
        self.version = (
            f"mode_v2_modehour{n_mode_hour_min}_mode{n_mode_min}_boot{bootstrap_iters}"
        )
        self.global_delays: list[int] = []
        self.by_mode: dict[str, list[int]] = {}
        self.by_mode_hour: dict[tuple[str, int], list[int]] = {}
        self._ingest(rows)

    def _ingest(self, rows: list[dict[str, str]]) -> None:
        by_mode: dict[str, list[int]] = {}
        by_mode_hour: dict[tuple[str, int], list[int]] = {}
        all_vals: list[int] = []
        for r in rows:
            d_raw = r.get("delay_sec")
            if d_raw in (None, ""):
                p = _parse_ts(r.get("planned_dep_ts"))
                rt = _parse_ts(r.get("realtime_dep_ts"))
                if not p or not rt:
                    continue
                d = int((rt - p).total_seconds())
            else:
                try:
                    d = int(float(d_raw))
                except ValueError:
                    continue
            mode = (r.get("mode") or "UNKNOWN").strip() or "UNKNOWN"
            hour_cph = self._row_hour_cph(r)
            all_vals.append(d)
            by_mode.setdefault(mode, []).append(d)
            if hour_cph is not None:
                by_mode_hour.setdefault((mode, hour_cph), []).append(d)
        self.global_delays = all_vals
        self.by_mode = by_mode
        self.by_mode_hour = by_mode_hour

    def _row_hour_cph(self, row: dict[str, str]) -> int | None:
        for key in ("hour_cph", "scheduled_hour_cph"):
            raw = row.get(key)
            if raw not in (None, ""):
                try:
                    return int(float(raw))
                except ValueError:
                    pass
        for key in ("obs_ts_cph", "depart_ts_cph", "planned_dep_ts", "realtime_dep_ts"):
            parsed = _parse_ts(row.get(key))
            if parsed is not None:
                return parsed.hour
        return None

    def _distribution_payload(self, vals: list[int], source: str) -> str:
        payload = {
            "source_level": source,
            "sample_size": len(vals),
            "min_delay_sec": min(vals) if vals else 0,
            "max_delay_sec": max(vals) if vals else 0,
        }
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)

    def _shrink_quantile(self, child_vals: list[int], parent_vals: list[int], p: float, k: float = 200.0) -> tuple[int, float]:
        if not child_vals:
            return (_percentile(parent_vals, p), 0.0)
        n = float(len(child_vals))
        w = n / (n + k)
        q_child = _percentile(child_vals, p)
        q_parent = _percentile(parent_vals, p)
        return (int(round(w * q_child + (1.0 - w) * q_parent)), round(w, 6))

    def estimate(
        self,
        *,
        line: str,
        mode: str,
        hour_cph: int | None = None,
        stop_type: str = "",
        context: dict | None = None,
    ) -> RiskEstimate:
        mode_vals = self.by_mode.get(mode, [])
        mode_hour_vals = self.by_mode_hour.get((mode, int(hour_cph)), []) if hour_cph is not None else []
        global_vals = self.global_delays

        if len(mode_hour_vals) >= self.n_mode_hour_min:
            vals = mode_hour_vals
            source = "mode_hour"
            parent = mode_vals if len(mode_vals) >= self.n_mode_min else global_vals
            shrinkage_parent_level = "mode" if len(mode_vals) >= self.n_mode_min else "global"
            p50, shrinkage_weight = self._shrink_quantile(vals, parent, 50)
            p90, _ = self._shrink_quantile(vals, parent, 90)
            p95, _ = self._shrink_quantile(vals, parent, 95)
        elif len(mode_vals) >= self.n_mode_min:
            vals = mode_vals
            source = "mode"
            shrinkage_parent_level = "global"
            p50, shrinkage_weight = self._shrink_quantile(vals, global_vals, 50)
            p90, _ = self._shrink_quantile(vals, global_vals, 90)
            p95, _ = self._shrink_quantile(vals, global_vals, 95)
        else:
            vals = global_vals
            source = "global"
            p50 = _percentile(vals, 50)
            p90 = _percentile(vals, 90)
            p95 = _percentile(vals, 95)
            shrinkage_parent_level = "none"
            shrinkage_weight = 1.0

        n = len(vals)
        p50_lo, p50_hi = _bootstrap_ci(vals, 50, self.bootstrap_iters, self.seed + 1)
        p90_lo, p90_hi = _bootstrap_ci(vals, 90, self.bootstrap_iters, self.seed + 2)
        if n < 200:
            p95_lo, p95_hi = (0, 0)
        else:
            p95_lo, p95_hi = _bootstrap_ci(vals, 95, self.bootstrap_iters, self.seed + 3)

        ci_width = max(0, p90_hi - p90_lo)
        if n < 80:
            confidence = "low"
        elif n < 200 or ci_width > 300:
            confidence = "medium"
        else:
            confidence = "high"
        evidence = "low" if n < 200 else ("medium" if n < 500 else "high")
        if n < 200:
            uncertainty_note = "P95 CI withheld because sample_size_effective < 200."
        elif source == "global":
            uncertainty_note = "Estimate falls back to global empirical distribution."
        elif source == "mode":
            uncertainty_note = "Estimate uses mode-level distribution with shrinkage toward global."
        else:
            uncertainty_note = "Estimate uses mode-hour distribution with hierarchical shrinkage."

        return RiskEstimate(
            delay_distribution=self._distribution_payload(vals, source),
            p50_delay_sec=p50,
            p90_delay_sec=p90,
            p95_delay_sec=p95,
            p50_ci_low=p50_lo,
            p50_ci_high=p50_hi,
            p90_ci_low=p90_lo,
            p90_ci_high=p90_hi,
            p95_ci_low=p95_lo,
            p95_ci_high=p95_hi,
            sample_size_effective=n,
            confidence_tag=confidence,
            evidence_level=evidence,
            source_level=source,
            ci95_width_sec=ci_width,
            risk_model_version=self.version,
            hour_cph=hour_cph,
            stop_type=stop_type,
            context_json=json.dumps(context or {}, ensure_ascii=True, sort_keys=True),
            shrinkage_parent_level=shrinkage_parent_level,
            shrinkage_weight=shrinkage_weight,
            uncertainty_note=uncertainty_note,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build mode-level risk estimates with bootstrap CI")
    parser.add_argument("--departures", required=True)
    parser.add_argument("--out", default="data/analysis/risk_model_mode_level.csv")
    parser.add_argument("--n-mode-hour-min", type=int, default=200)
    parser.add_argument("--n-line-min", type=int, default=None, help="Deprecated alias for --n-mode-hour-min")
    parser.add_argument("--n-mode-min", type=int, default=500)
    parser.add_argument("--bootstrap-iters", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = _read_rows(Path(args.departures))
    n_mode_hour_min = args.n_mode_hour_min if args.n_line_min is None else args.n_line_min
    model = ModeLevelRiskModel(
        rows,
        n_mode_hour_min=n_mode_hour_min,
        n_mode_min=args.n_mode_min,
        bootstrap_iters=args.bootstrap_iters,
        seed=args.seed,
    )

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in rows:
        line = (r.get("line") or "UNKNOWN").strip() or "UNKNOWN"
        mode = (r.get("mode") or "UNKNOWN").strip() or "UNKNOWN"
        key = (line, mode)
        if key in seen:
            continue
        seen.add(key)
        hour_cph = model._row_hour_cph(r)
        stop_type = (r.get("stop_type") or "").strip()
        context = {"mode": mode, "line": line}
        est = model.estimate(line=line, mode=mode, hour_cph=hour_cph, stop_type=stop_type, context=context)
        out.append(
            {
                "line": line,
                "mode": mode,
                "hour_cph": "" if hour_cph is None else hour_cph,
                "stop_type": stop_type,
                "delay_distribution": est.delay_distribution,
                "p50_delay_sec": est.p50_delay_sec,
                "p90_delay_sec": est.p90_delay_sec,
                "p95_delay_sec": est.p95_delay_sec,
                "p50_ci_low": est.p50_ci_low,
                "p50_ci_high": est.p50_ci_high,
                "p90_ci_low": est.p90_ci_low,
                "p90_ci_high": est.p90_ci_high,
                "p95_ci_low": est.p95_ci_low,
                "p95_ci_high": est.p95_ci_high,
                "sample_size_effective": est.sample_size_effective,
                "confidence_tag": est.confidence_tag,
                "evidence_level": est.evidence_level,
                "source_level": est.source_level,
                "ci95_width_sec": est.ci95_width_sec,
                "risk_model_version": est.risk_model_version,
                "shrinkage_parent_level": est.shrinkage_parent_level,
                "shrinkage_weight": est.shrinkage_weight,
                "uncertainty_note": est.uncertainty_note,
            }
        )
    out.sort(key=lambda x: (x["mode"], x["line"]))
    _write_rows(
        Path(args.out),
        out,
        [
            "line",
            "mode",
            "hour_cph",
            "stop_type",
            "delay_distribution",
            "p50_delay_sec",
            "p90_delay_sec",
            "p95_delay_sec",
            "p50_ci_low",
            "p50_ci_high",
            "p90_ci_low",
            "p90_ci_high",
            "p95_ci_low",
            "p95_ci_high",
            "sample_size_effective",
            "confidence_tag",
            "evidence_level",
            "source_level",
            "ci95_width_sec",
            "risk_model_version",
            "shrinkage_parent_level",
            "shrinkage_weight",
            "uncertainty_note",
        ],
    )
    print(args.out)


if __name__ == "__main__":
    main()
