#!/usr/bin/env bash
set -euo pipefail

echo "Deprecated: use infra/gcp/deploy_collector_job.sh"
exec bash infra/gcp/deploy_collector_job.sh "$@"
