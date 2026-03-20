# cph-robust-transfers

Robust transfer analysis pipeline for Copenhagen transit networks.

This repository now also follows the documentation/control-file shape of the hybrid Codex template:

- top-level project framing: `AGENTS.md`, `codex.md`, `problem.md`, `experiments.md`
- workflow docs: `docs/workflow/`
- research/model notes: `model/`
- physical bridge packages: `src/app`, `src/optimization`
- semantic data roots: `data/raw`, `data/processed`

## Repository layout
- `src/gtfs_ingest/`: GTFS download and parsing
- `src/graph/`: static stop graph build and metrics
- `src/robustness/`: disruption simulations and summaries
- `src/realtime/`: realtime collector, parser, throttling, quantile script
- `configs/`: pipeline defaults, station seeds, SQL templates
- `infra/gcp/`: bootstrap/deploy/scheduler/secret scripts
- `infra/bigquery/`: structured load and quantile query scripts
- `docs/`: architecture, workflow, decisions, reports
- `model/`: formulation and solver/execution notes
- `src/app/`: template-style application bridge layer over current pipelines
- `src/accessibility/`: quota-aware accessibility product proxy/cache/transform scaffold
- `src/optimization/`: template-style optimization bridge layer over current robustness/routing code
- `data/raw/`: template-style raw-data semantic root
- `data/processed/`: template-style processed-data semantic root
- `docs/research_dashboard.html`: offline executive dashboard with line filtering and GTFS-derived exposure map
- `docs/accessibility_product_plan.md`: formal implementation plan for the map-first accessibility product
- `web/accessibility/`: frontend shell for the future reachability map app
- `src/app/cli.py`: template-style unified application CLI
- `src/optimization/api.py`: template-style unified optimization API
- `src/optimization/cli.py`: template-style unified optimization CLI
- `docs/next_phase_plan.md`: canonical A -> B -> C -> D execution plan

## Template-oriented entry points
- `problem.md`: project problem framing
- `experiments.md`: reproducible milestone log
- `docs/workflow/software.md`: software / infra changes
- `docs/workflow/optimization.md`: analysis / modeling changes
- `model/formulation.md`: analysis structure and metrics
- `model/solver.md`: execution and acceptance logic

## Physical Mapping
- Existing runtime modules remain valid in `src/realtime`, `src/robustness`, `src/gtfs_ingest`, and `src/graph`.
- Template-style imports can now target `src/app` and `src/optimization` without moving production code.
- Existing data paths remain valid; `data/raw` and `data/processed` act as semantic anchors and mapping docs rather than forced migrations.
- Template-style CLIs now exist:
  - `python -m src.app.cli ...`
  - `python -m src.optimization.cli ...`

## Quickstart
```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m src.app.results_dashboard --out docs/research_dashboard.html
python3 -m unittest tests.test_accessibility_scaffold
python3 -m src.accessibility.server serve --host 127.0.0.1 --port 8765
```

Main workflow is documented in `docs/runbook.md`.

## Security
- Never commit API keys.
- Keep `REJSEPLANEN_API_KEY` only in env vars or Secret Manager.
