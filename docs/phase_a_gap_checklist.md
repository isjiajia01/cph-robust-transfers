# Phase A 差异清单（当前代码 vs `docs/next_phase_plan.md`）

## 已完成

1. Collector 已使用可复现 `run_id`，基于 `scheduled_ts_utc -> YYYYMMDDTHHMM`。
2. `observations` 已补齐 Phase A 目标字段：`scheduled_ts_utc`、`trigger_id`、`job_start_ts_utc`、`job_end_ts_utc`、`run_status`、`collector_version`，并保留 `ingest_ts_utc`、`sampling_target_version`。
3. `api_errors` 表已存在，且已经包含扩展证据字段：`ingest_ts_utc`、`request_id`、`is_retry_final`。
4. `run_metrics` 表已存在，且包含运行时长、请求计数、状态码计数、`collector_version`、`sampling_target_version`。
5. 已存在 `run_gap_diagnostics` 视图，输出 `gap_sec`、`cold_start_proxy_sec`、`api_error_ratio`、`dominant_error_code`、`run_overrun`、`scheduler_miss_proxy`、`has_throttle_signal`、`rule_fired`、`likely_cause`。
6. Task A 产出的 `gap_diagnostics` 已固定为结构化证据块：`rows` + `row_count`。
7. Task A markdown 摘要已专门展示 `Gap Diagnostics (Top 5)` 证据。
8. 已存在 `*_enriched` 视图，并使用 `Europe/Copenhagen` 派生时间字段。
9. Task A 已写 `summary.json` 到 `dt=...` 与 `latest`。
10. 已存在 `daily_summary` 表。
11. `summary.json` 已包含 `sampling_24h`、`gap_diagnostics`、`top_lines_by_p95`。
12. 已补齐 Phase A 专项测试：
   - collector observation/run_metrics helper
   - `run_gap_diagnostics` SQL 证据字段
   - `summary.json` 的 `gap_diagnostics` contract
13. 已通过验证：
   - `python3 -m unittest tests.test_realtime_collector tests.test_phase_a_task_a tests.test_realtime_parser tests.test_delay_quantiles tests.test_template_bridges tests.test_template_cli`
   - `python3 -m py_compile src/realtime/collector.py src/realtime/task_a_daily_job.py src/realtime/update_week3_summary.py`

## 部分完成

1. 无。当前代码与 Phase A 计划的工程化证据链要求已经对齐。

## 未完成

1. 无。Phase A 已完成。
