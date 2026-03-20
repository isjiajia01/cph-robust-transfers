# 11.01 项目下一阶段执行计划（A→B→C→D）

## Summary

1. 目标是把项目从“能跑”提升为“可证据化、可归因、可复现、可展示”。
2. 执行顺序采用 A→B→C→D，并在 C 中采用 mode-level `RiskModel` 作为默认占位实现。
3. 先完成 A 的工程化证据链，再并行推进 B 的静态 OR 成果固化，随后落 C 的可替换算法框架，最后在 D 中加入少样本不确定性表达。
4. 交付物以 GCP 定时任务 + BigQuery 表/视图 + docs/notebooks 图文证据 为主，保证面试可演示。

## A. 采样系统工程化（最高优先级）

1. 数据模型改造（Collector 输出层）。
2. `observations` 增加字段：`scheduled_ts_utc`、`trigger_id`、`job_start_ts_utc`、`job_end_ts_utc`、`run_status`、`collector_version`。
3. 额外固化两个完整性字段：`ingest_ts_utc`、`sampling_target_version`。
4. `run_id` 固定为可复现主键：默认使用 `scheduled_ts_utc -> YYYYMMDDTHHMM`。
5. 新增 `api_errors` 表，字段固定为：`obs_ts_utc`、`run_id`、`trigger_id`、`endpoint`、`http_code`、`error_code`、`message`、`station_id`、`journey_ref`、`latency_ms`、`retry_count`。
6. `api_errors` 额外增加：`request_id`、`is_retry_final`。
7. 新增 `run_metrics` 表，字段固定为：`run_id`、`trigger_id`、`scheduled_ts_utc`、`job_start_ts_utc`、`job_end_ts_utc`、`duration_sec`、`station_count`、`board_request_count`、`journey_request_count`、`success_count`、`error_count`、`status_2xx_count`、`status_4xx_count`、`status_5xx_count`。
8. Gap 归因逻辑（BigQuery 层）。
9. 新增归因视图 `run_gap_diagnostics`，输出 `gap_sec`、`cold_start_proxy_sec`、`api_error_ratio`、`dominant_error_code`、`rule_fired`、`likely_cause`（枚举：`scheduler_miss` / `run_overrun` / `api_throttle` / `network_or_unknown`）。
10. 额外固化可解释证据列：`run_overrun`、`scheduler_miss_proxy`。
11. 时区安全。
12. 强制所有时段分析使用 `*_enriched` 视图中的 `obs_ts_cph` / `hour_cph` / `dow_cph`，并在 SQL 模板中禁用 UTC 小时直接聚合。
13. 定时任务编排。
14. Task A 每日执行内容固定为：刷新 quantiles、刷新完整性、刷新 gap 归因、写 `summary.json` 到 `dt=YYYY-MM-DD` 与 `latest`、写入 `daily_summary` 表。
15. Task A cron 默认使用 `Europe/Copenhagen` 时区，不使用固定 UTC 本地日切片。
16. 验收标准。
17. 连续 24h 后可计算 `coverage_ratio`、`critical_gap_count`、`max_gap_sec` 且能追溯到具体 `run_id` / `trigger_id`。
18. 任意一次缺口都能在 `api_errors` 或 `run_metrics` 中找到可解释证据。
19. `summary.json` 必含 `sampling_24h`、`gap_diagnostics`、`top_lines_by_p95` 三块。
20. 同一采样实体必须具备幂等/去重主键，不允许重复样本污染统计结果。

## B. 静态 GTFS OR 成果固化（不依赖实时，立即推进）

1. 图建模与验证。
2. 固化 stop-level 图构建参数与版本输出目录，要求每次输出包含 `graph_manifest.json`（数据日期、节点数、边数、过滤规则）。
3. `graph_manifest.json` 额外要求包含：`gtfs_feed_version`、`build_params_hash`、`stop_count_filtered`、`edge_count_filtered`。
4. 鲁棒性实验输出标准化。
5. 固定产出 3 件核心交付物：关键枢纽地图、random vs targeted 曲线、top-10 脆弱枢纽解释表。
6. 结果叙事模板。
7. 每个 top-10 节点必须附带 `degree`、`betweenness`、`impact_delta_lcc`、`潜在规划含义` 4 列。
8. 每批 OR 图表需要配套 `results/robustness/README.md` 解释“如何读图 + 规划意义”。
9. 验收标准。
10. 在无实时数据前提下可独立运行并生成可发布图表与 markdown 摘要。

## C. 鲁棒换乘模型与路由器框架（可替换风险组件）

1. 接口先行，数据后置。
2. 新增 `RiskModel` 接口契约：输入 `line|mode|hour_cph|stop_type|context`，输出 `delay_distribution`、`p50/p90/p95`、`sample_size`、`confidence_tag`。
3. 默认实现采用 mode-level。
4. 首版 `ModeLevelRiskModel` 使用 `mode + hour_cph` 的经验分布，样本不足时回退到 `mode`，再回退到 `global`。
5. 默认阈值固定为：`n_line < 200 -> mode`，`n_mode < 500 -> global`。
6. 路由/换乘引擎参数化。
7. 明确定义 `slack`、`minimum_transfer_time`、`walk_time_assumption`、`missed_transfer_rule`，全部配置化到 `configs/`。
8. 可替换性约束。
9. 路由器仅依赖接口，不直接读取 BQ 表结构，后续替换 line-level 模型无需改路由主流程。
10. 标准输出表固定包含：`od_id`、`depart_ts_cph`、`path_id`、`travel_time_min`、`transfers`、`miss_prob`、`cvar95_min`、`evidence_level`、`sample_size_effective`、`risk_model_version`。
11. 验收标准。
12. 在当前数据量下可运行并输出一组 Pareto 样例结果（例如 `travel_time vs miss_risk`）。

## D. 不确定性表达（少数据可科学解释）

1. 指标层增加不确定性输出。
2. 对关键延误分位数输出 bootstrap CI（默认 1000 次重采样）。
3. 小样本时对 `P95` 采用硬门槛：`n < 200` 时不输出稳定 CI，标记为低证据。
4. 分层收缩策略。
5. 增加 Bayesian shrinkage（层级顺序固定：`global -> mode -> line`），当 line 样本不足时自动向上层收缩。
6. 工程实现上优先使用可解释、可复现的参数化近似，而非难以维护的直接分位数层级建模。
7. 报告语义标准。
8. 所有结论必须带 `evidence_level`（`low/medium/high`）与 `sample_size`，避免过度结论。
9. 验收标准。
10. `summary.json` 和 `docs/week3_summary.md` 都能显示“点估计 + 区间 + 证据等级”。

## Public APIs / Interfaces / Schemas 变更清单

1. Collector 结构化输出 schema 增加 `scheduled_ts_utc`、`trigger_id`、`job_start_ts_utc`、`job_end_ts_utc`、`run_status`、`collector_version`。
2. 新增 BigQuery 表 `api_errors`、`run_metrics`、`daily_summary`。
3. 新增 BigQuery 视图 `run_gap_diagnostics`（归因结果）。
4. 新增 Python 接口 `RiskModel`（mode-level 默认实现）。
5. `summary.json` schema 扩展字段：`gap_diagnostics`、`uncertainty`、`evidence_level`。

## Test Cases and Scenarios

1. 单元测试。
2. collector 在 `2xx`、`4xx`、`5xx`、`429`、超时场景下，`api_errors` 写入完整。
3. `run_metrics` 计算 `duration_sec`、状态码计数、成功失败计数准确。
4. `risk_model` 回退链路正确（line 缺样本时回退 mode/global）。
5. 集成测试。
6. 一次 Task A dry run 后，GCS 同时存在 `dt` 与 `latest` 的 `summary.json`，且字段齐全。
7. `run_gap_diagnostics` 对模拟缺口能返回明确 `likely_cause`。
8. 回归测试。
9. 现有 Week1/Week2 产出脚本与图表路径不破坏。
10. `*_enriched` 视图的 `hour_cph` 与 UTC 差值在当天时区规则下正确。

## Rollout / Monitoring

1. 阶段 1（A 完成后）。
2. 先灰度 1 天，仅观察 `api_errors` 体量与 `run_metrics` 延迟分布。
3. 阶段 2（稳定后）。
4. 打开正式日更 Task A；阈值告警：`coverage_ratio < 0.9`、`critical_gap_count > 0`、`429 比例 > 5%`。
5. 阶段 3（B/C/D）。
6. 每日自动产出 OR 图表摘要与风险模型稳定性摘要，周维度复核。
7. 成本护栏：
   - quantiles 只扫最近 N 天分区
   - integrity / gap 默认只扫最近 24h
   - `journeyDetail` 请求量需受采样比例和配额限制约束

## Assumptions and Defaults

1. 默认采样频率保持 `3 min` 不变。
2. Task A 每日本地时间保持 `02:20 Europe/Copenhagen`。
3. 时区分析统一使用 `Europe/Copenhagen` 派生字段。
4. mode-level `RiskModel` 作为 C 的默认占位实现。
5. 当样本不足时优先保证“可解释 + 可回退”，而不是追求细粒度排名。
6. 本计划不包含额外产品 UI，仅包含数据与分析产线、文档、图表、notebook 交付。
