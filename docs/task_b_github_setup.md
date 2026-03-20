# Task B GitHub Actions Setup

Workflow: `.github/workflows/week3-docs-update.yml`

## Required GitHub Secrets

- `WEEK3_REPORT_BUCKET`
  - Value: `cph-robust-transfers-260302-cph-rt-raw`
- `GCP_WIF_PROVIDER`
  - Workload Identity Provider resource name (from GCP IAM workload identity setup)
- `GCP_WIF_SA`
  - Service account email used by GitHub Actions (recommended: dedicated readonly/report SA)

## Runtime Behavior

- Schedule: `40 1 * * *` (UTC) + manual `workflow_dispatch`
- Steps:
  1. Auth to GCP via WIF
  2. Download `gs://<bucket>/reports/week3/latest/summary.json`
  3. Render `docs/week3_summary.md`
  4. Commit & push if changed

## Validation Checklist

1. Trigger workflow manually once from GitHub Actions UI.
2. Confirm run succeeds and `docs/week3_summary.md` updates.
3. Confirm next scheduled run appears in Actions history.
4. If no changes in summary content, workflow should exit with "No doc changes." and no commit.
