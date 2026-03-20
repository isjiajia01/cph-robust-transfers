# Model Formulation

## Static Network Layer

### Sets

- `V`: transit stops
- `E`: directed stop-to-stop connections

### Core metrics

- degree / hub ranking
- connected component structure
- reachable OD ratio
- average shortest path on the largest connected component

## Robustness Layer

### Failure modes

- random node removals
- targeted node removals by estimated betweenness

### Outputs

- LCC ratio curve
- reachable OD degradation
- path-length degradation

## Realtime Reliability Layer

### Inputs

- planned departure timestamp
- realtime departure timestamp
- line and mode
- run-level sampling metadata

### Derived quantities

- `delay_sec`
- hour-of-day and day-of-week reliability summaries
- line-level tail-delay ranking
- `evidence_level`
- bootstrap confidence intervals
- fallback-aware risk distributions
- shrinkage metadata (`source_level`, `shrinkage_parent_level`, `shrinkage_weight`)

## Router / Risk Layer

### Goal

Use realtime-derived delay behavior to score candidate transfers or routes under uncertainty.

### Interface Contract

Input:

- `line`
- `mode`
- `hour_cph`
- `stop_type`
- `context`

Output:

- `delay_distribution`
- `p50_delay_sec`
- `p90_delay_sec`
- `p95_delay_sec`
- `sample_size`
- `confidence_tag`
- `evidence_level`
- uncertainty interval fields for key quantiles
- an uncertainty note when high-quantile CI is withheld

### Current artifacts

- `data/analysis/risk_model_mode_level.csv`
- `data/analysis/router_pareto_table.csv`

### Default fallback chain

- mode + hour
- otherwise mode
- otherwise global
