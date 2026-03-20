# Optimization Workflow

1. Read `problem.md` and the current analytical outputs in `docs/` and `data/analysis/`.
2. Check the active stage in `docs/next_phase_plan.md`:
   - B for static OR hardening
   - C for replaceable risk-model/router work
   - D for uncertainty and shrinkage
3. Decide whether the task belongs to:
   - static graph robustness
   - realtime delay analysis
   - transfer-risk / routing
4. Keep experiments reproducible:
   - record input files
   - record date/window
   - record outputs and figures
5. Update `experiments.md` and `docs/decisions.md` when the analysis workflow changes.
6. If results depend on live data, confirm collection status before interpreting gaps as system behavior.
7. Default to the mode-level fallback chain unless the task explicitly upgrades the `RiskModel` implementation:
   - `mode + hour_cph`
   - fallback to `mode`
   - fallback to `global`
8. Keep router assumptions in `configs/router.defaults.toml`; do not hardcode `slack`, `minimum_transfer_time`, or walk assumptions in notebooks/scripts.
