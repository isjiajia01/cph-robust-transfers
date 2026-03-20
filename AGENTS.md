# AGENTS.md

## Project Type
Hybrid project combining:

- data engineering
- transit network analysis
- robustness and routing research

## Work Modes
Choose mode by task intent:

- If task mentions collector, API, GCP, scheduler, BigQuery, bug, test, deploy, use **Software mode**.
- If task mentions robustness model, routing, risk model, experiment, notebook findings, use **Optimization mode**.
- If a task spans both, stabilize the software path first, then run analysis.

## Workflows

### 1) Software development
Follow: `docs/workflow/software.md`

### 2) Optimization research
Follow: `docs/workflow/optimization.md`

## Folder Responsibilities

- `src/gtfs_ingest`: static GTFS ingestion
- `src/graph`: graph build and network metrics
- `src/realtime`: realtime sampling, parsing, reporting
- `src/robustness`: robustness experiments and router/risk analysis
- `configs`: runtime configs, station seeds, SQL templates
- `infra`: GCP, BigQuery, docs automation
- `model`: analytical formulation and solver/research notes
- `data`: generated data artifacts and exports
- `docs`: architecture, decisions, workflow, reports
- `tests`: automated validation

## Safety Rules

- Never commit API keys.
- Never re-enable live collection without explicit user approval.
- Never delete historical data artifacts unless explicitly asked.
- Never break collector or BigQuery schemas without updating docs and tests.

## Template Evolution Rules

- Keep `docs/workflow.md` and `docs/decisions.md` append-first.
- Add small reusable process updates instead of rewriting large sections.
- Prefer documenting how the current repo maps to the template rather than renaming stable production code.
