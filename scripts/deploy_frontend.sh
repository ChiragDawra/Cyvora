#!/usr/bin/env bash
# Builds the Next.js static export against the live API and publishes it to the frontend
# S3 bucket behind CloudFront.
#
# The API URL has to be known at BUILD time, not runtime: next.config.ts uses
# output: "export", and Next.js inlines NEXT_PUBLIC_* into the bundle during the build.
# So the order is always: terraform apply -> read outputs -> build -> sync -> invalidate.
#
# Usage (locally):  ./scripts/deploy_frontend.sh
# CI runs the same steps inline - see .github/workflows/deploy.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT/infra"

API_URL="$(terraform output -raw api_url)"
FRONTEND_BUCKET="$(terraform output -raw frontend_bucket_name)"
DISTRIBUTION_ID="$(terraform output -raw cloudfront_distribution_id)"

echo "API:          $API_URL"
echo "Bucket:       s3://$FRONTEND_BUCKET"
echo "Distribution: $DISTRIBUTION_ID"

cd "$REPO_ROOT/frontend"
NEXT_PUBLIC_API_URL="$API_URL" npm run build

# --delete drops files from previous builds (Next.js emits content-hashed asset names, so
# stale ones would otherwise accumulate forever in a bucket nobody prunes).
aws s3 sync out/ "s3://$FRONTEND_BUCKET" --delete

# CloudFront caches aggressively via the CachingOptimized policy. Without an
# invalidation, index.html keeps serving the previous build until the TTL expires.
# The free tier covers 1,000 invalidation paths/month; "/*" counts as one path.
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text

cd "$REPO_ROOT/infra"
echo
echo "Deployed: https://$(terraform output -raw cloudfront_domain)"
