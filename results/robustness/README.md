# Robustness Results

- `key_hubs_map.png`: baseline hub ranking proxy from Week1.
- `random_vs_targeted_curve.png`: LCC ratio vs removed-node percentage.
- `extra_metrics_curve.png`: reachable OD ratio and average shortest path trends.
- `top10_vulnerable_nodes.csv`: nodes with highest single-node LCC impact.
- `summary.md`: fixed narrative summary for interview/demo use.
- `graph_manifest.json`: graph build metadata and filtering rules.
- Read targeted vs random as fragility evidence: faster targeted decay implies hub bottlenecks.
- Use top-10 table with planning implication notes to map candidate interventions.
- Curves are comparable only under the same graph build + simulation params.
- Re-run from scripts to keep web/portfolio artifacts reproducible.
