#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <PROJECT_ID>"
  exit 1
fi

PROJECT_ID="$1"
gcloud config set project "$PROJECT_ID"

echo "Paste REJSEPLANEN API key then press Enter (input hidden):"
stty -echo
read -r API_KEY
stty echo
echo

if ! gcloud secrets describe REJSEPLANEN_API_KEY >/dev/null 2>&1; then
  gcloud secrets create REJSEPLANEN_API_KEY --replication-policy=automatic
fi
printf "%s" "$API_KEY" | gcloud secrets versions add REJSEPLANEN_API_KEY --data-file=- >/dev/null

echo "Secret updated: REJSEPLANEN_API_KEY"
