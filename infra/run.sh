#!/usr/bin/env bash
# Wrapper so `terraform` gets AWS credentials and the feed API keys from ../.env
# without retyping `set -a && source ../.env && set +a` every time.
# Usage: ./run.sh plan | ./run.sh apply | ./run.sh apply -target=... etc.
set -euo pipefail

cd "$(dirname "$0")"

set -a
source ../.env
set +a

export TF_VAR_abusech_auth_key="$ABUSECH_AUTH_KEY"
export TF_VAR_abuseipdb_api_key="$ABUSEIPDB_API_KEY"

terraform "$@"
