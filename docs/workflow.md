# Workflow (living document)

## Defaults

- Prefer minimal code diffs and preserve working infra.
- Distinguish clearly between Software and Optimization tasks.
- Update `agent.md` after any meaningful infra or process change.
- For production-like changes, verify with a real command or smoke test when possible.
- Treat `docs/next_phase_plan.md` as the default execution-order and acceptance reference.

## Commands

- Tests: `python3 -m unittest discover -s tests -p 'test_*.py'`
- Collector deploy: `bash infra/gcp/deploy_collector_job.sh "$PROJECT_ID" "$REGION" "$REJSEPLANEN_BASE_URL"`
- Manual collector smoke test: `gcloud run jobs execute cph-rt-collector --region "$REGION" --project "$PROJECT_ID" --wait`
- Week3 acceptance check: `bash infra/bigquery/check_week3_acceptance.sh "$PROJECT_ID" cph_rt europe-north1 0.90 0 0.05`
- Next-phase reference: `docs/next_phase_plan.md`

## Template Patch Log

## Template Patch (2026-03-06)
Change:
- [Add] Rule: Hybrid planning docs should converge into one canonical execution-plan markdown instead of scattered future-state notes.
- [Add] Rule: Engineering plans must encode deterministic IDs, attribution evidence columns, timezone-safe defaults, and rollout guardrails.
- [Add] Rule: Optimization planning should declare a default fallback model and fixed sample thresholds before pursuing finer-grained variants.

Reason:
- The project needs a single future-state source of truth that is operational enough for implementation and clear enough for interviews.

Applies to:
- Both

Verification:
- Check that `problem.md`, `experiments.md`, `docs/decisions.md`, `model/`, and workflow docs all point back to the same next-phase plan.

Links:
- docs/next_phase_plan.md
- docs/decisions.md
- model/formulation.md
- model/solver.md

## Template Patch (2026-03-06)
Change:
- [Add] Convention: Align hybrid-template structure through docs and control files before moving production directories.
- [Add] Rule: For GCP data pipelines, validate both scheduler activity and warehouse freshness before declaring collection healthy.
- [Add] Rule: When sufficient data is reached and the user asks to stop collection, pause schedulers instead of deleting jobs.

Reason:
- This repo already had working pipelines and historical artifacts; preserving runtime stability mattered more than cosmetic directory parity.

Applies to:
- Both

Verification:
- Check that the repo has template-style top-level docs and that the production pipeline still runs or remains intentionally paused.

Links:
- AGENTS.md
- codex.md
- docs/decisions.md
- infra/gcp/create_scheduler.sh
- src/realtime/collector.py
