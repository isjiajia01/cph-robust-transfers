# Week3 Conclusions (Preliminary)

- Window: last `7` day(s) from BigQuery `departures_enriched`
- Effective observations across ranked lines: `1144`
- Timezone: `Europe/Copenhagen` (`hour_cph`, `dow_cph`)

## Reliability Ranking (Best P95 Delay)
- E: P50=60s, P90=60s, P95=60s, n=131
- H: P50=60s, P90=60s, P95=60s, n=17
- Lokalbane 960R: P50=60s, P90=60s, P95=60s, n=14
- Re 1055: P50=60s, P90=60s, P95=60s, n=12
- Re 1069: P50=60s, P90=60s, P95=60s, n=6
- Re 1065: P50=60s, P90=60s, P95=60s, n=4
- Re 2522: P50=60s, P90=60s, P95=60s, n=3
- Re 226: P50=60s, P90=60s, P95=60s, n=3
- Re 1541: P50=60s, P90=60s, P95=60s, n=3
- Re 1058: P50=60s, P90=60s, P95=60s, n=3

## Reliability Ranking (Worst P95 Delay)
- Re 4516: P50=600s, P90=780s, P95=780s, n=5
- Re 4541: P50=540s, P90=660s, P95=660s, n=21
- Re 1059: P50=480s, P90=480s, P95=480s, n=4
- IC 141: P50=240s, P90=360s, P95=360s, n=7
- Re 4422: P50=60s, P90=240s, P95=300s, n=11
- Re 4426: P50=60s, P90=300s, P95=300s, n=6
- Re 2518: P50=240s, P90=300s, P95=300s, n=6
- Re 1061: P50=240s, P90=300s, P95=300s, n=10
- Re 1049: P50=300s, P90=300s, P95=300s, n=7
- Re 1045: P50=300s, P90=300s, P95=300s, n=3

## Outputs
- `docs/figures/week3_p95_by_hour_cph.png`
- `docs/figures/week3_p95_by_dow_cph.png`
- `docs/figures/week3_line_reliability_rank.png`
- `data/analysis/week3_hour_dow_quantiles.csv`
- `data/analysis/week3_line_reliability_rank.csv`
- Pareto table: `data/analysis/router_pareto_table.csv`
- Risk model table: `data/analysis/risk_model_mode_level.csv`
