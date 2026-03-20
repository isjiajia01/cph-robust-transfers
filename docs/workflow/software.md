# Software Workflow

1. Identify the operational surface:
   - local scripts
   - Cloud Run / Scheduler / BigQuery
   - generated docs or reports
   - current phase in `docs/next_phase_plan.md` (A before B/C/D for engineering changes)
2. Inspect current implementation before proposing structure changes.
3. Prefer minimal diffs that keep current paths and deployment scripts valid.
4. For infra-sensitive changes, verify both:
   - command execution status
   - data freshness in downstream storage/warehouse
5. Update `README.md`, `docs/decisions.md`, and `agent.md` when behavior changes.
6. When touching collector/reporting schemas, preserve deterministic IDs, attribution evidence, and timezone-safe analysis defaults.
