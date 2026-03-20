#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 <REPO_OWNER/REPO_NAME> <REPORT_BUCKET> <GCP_WIF_PROVIDER> <GCP_WIF_SA>"
  echo "Example: $0 isjiajia01/cph-robust-transfers cph-robust-transfers-260302-cph-rt-raw projects/123/locations/global/workloadIdentityPools/pool/providers/provider github-actions-sa@cph-robust-transfers-260302.iam.gserviceaccount.com"
  exit 1
fi

REPO="$1"
REPORT_BUCKET="$2"
WIF_PROVIDER="$3"
WIF_SA="$4"

gh secret set WEEK3_REPORT_BUCKET --repo "$REPO" --body "$REPORT_BUCKET"
gh secret set GCP_WIF_PROVIDER --repo "$REPO" --body "$WIF_PROVIDER"
gh secret set GCP_WIF_SA --repo "$REPO" --body "$WIF_SA"

echo "repo=$REPO"
echo "set_secrets=WEEK3_REPORT_BUCKET,GCP_WIF_PROVIDER,GCP_WIF_SA"
echo "next=run GitHub Action 'Week3 Docs Update' via workflow_dispatch once to validate"
