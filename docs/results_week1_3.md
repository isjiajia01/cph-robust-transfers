# Results Week1-3

## Week1: GTFS -> Static Graph Baseline

### Inputs and pipeline
- GTFS source: `https://www.rejseplanen.info/labs/GTFS.zip`
- Raw snapshot: `data/gtfs/raw/gtfs_20260302T085705Z.zip`
- Parsed tables: `data/gtfs/parsed/20260302/`
- Graph outputs: `data/graph/20260302/edges.csv`, `data/graph/20260302/nodes.csv`, `data/graph/20260302/metrics.csv`

### Core network stats
- Stops (nodes): `36,871`
- Directed edges: `50,141`
- Largest connected component (undirected projection): `22,342` (`60.60%` of nodes)

### Top hubs (degree)
- Skive Trafikterminal (`000779079101`) degree=`42`
- Odder Busterminal (`000727000701`) degree=`35`
- Randers Busterminal (`000731601003`) degree=`35`
- Hadsten St./Østergade (`000709000701`) degree=`27`
- Middelfart Station (Middelfart Kommune) (`000410187400`) degree=`22`

### Figures
- Hub ranking: `docs/figures/week1_top_hubs.png`
- Connectivity profile: `docs/figures/week1_component_sizes.png`
- Notebook: `notebooks/01_static_network_baseline.ipynb`

## Week2: Robustness (Random vs Targeted)

### Inputs and pipeline
- Graph input: `data/graph/20260302/edges.csv`, `data/graph/20260302/nodes.csv`
- Simulation runs: `data/robustness/20260302_enhanced/robustness_runs.csv`
- Summary: `data/robustness/20260302_enhanced/robustness_summary.csv`
- Critical nodes: `data/robustness/20260302_enhanced/critical_nodes_top10.csv`
- Figure: `docs/figures/week2_random_vs_targeted.png`
- Extra metrics figure: `docs/figures/week2_extra_metrics.png`

### Experiment settings
- Removal levels: `k = 3%..30%` with `step=3`
- Random failure repeats per k: `10`
- Targeted attack repeats per k: `1`
- Targeting rule: descending **betweenness** (approximate, sampled sources)
- Additional metrics: `reachable_od_ratio`, `avg_shortest_path` (on largest connected component)

### Key findings
- At `k=9%`: random LCC ratio avg=`0.835`, targeted=`0.580`
- At `k=15%`: random LCC ratio avg=`0.656`, targeted=`0.140`
- At `k=30%`: random LCC ratio avg=`0.094`, targeted=`0.031`
- Targeted removals by betweenness still degrade connectivity faster than random failures.

## Week3: Realtime Pipeline + Delay Profiling

### Operational status
- Cloud Run job deployed and executed with updated parser (`delay_sec`, `delay_arr_sec`, `delay_dep_sec` computed).
- Latest validated execution: `run_id=20260302T1118`.
- Resolved stations: `20` (validated `stopExtId` list in `configs/stations_seed.csv`).

### Data outputs
- Raw layer (GCS): `gs://cph-robust-transfers-260302-cph-rt-raw/realtime_raw/dt=2026-03-02/run_id=20260302T1118/`
- Structured layer (GCS): `gs://cph-robust-transfers-260302-cph-rt-structured/structured/dt=2026-03-02/run_id=20260302T1118/`
- BigQuery tables refreshed: `cph_rt.departures`, `cph_rt.journey_stops`, `cph_rt.observations`

### Week3 analysis artifacts
- BQ quantiles export: `data/analysis/delay_quantiles_bq.csv`
- Local departures snapshot: `data/analysis/departures_20260302T093647Z.csv`
- Summary: `docs/week3_summary.md`
- `docs/figures/week3_delay_quantiles_by_line.png`
- `docs/figures/week3_delay_p95_by_hour.png`
- Notebook: `notebooks/03_realtime_delay_profile.ipynb`

### Current finding
- Delay distribution is now measurable end-to-end; multiple lines show non-zero realtime departure drift, with a long-tail visible in P95.

### Remaining Week3 TODO
- Run scheduler continuously for `24-48h` and verify no data gaps in `cph_rt.observations`.
- Increase `max_journey_detail_per_cycle` based on quota headroom to improve transfer-risk coverage.
- Daily BigQuery Task A job now exports quantiles/integrity/gaps and summary artifacts.
- Gap diagnostics now tracks likely cause and rule_fired; Cloud Logging alert setup is scripted in `infra/gcp/setup_week3_alerts.sh` (pending apply per project).


### Week3 conclusion artifacts (new)
- `docs/week3_conclusions.md`
- `docs/figures/week3_p95_by_hour_cph.png`
- `docs/figures/week3_p95_by_dow_cph.png`
- `docs/figures/week3_line_reliability_rank.png`
- `data/analysis/week3_hour_dow_quantiles.csv`
- `data/analysis/week3_line_reliability_rank.csv`
- `data/analysis/router_pareto_table.csv`
- `data/analysis/risk_model_mode_level.csv`
