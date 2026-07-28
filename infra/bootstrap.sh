#!/usr/bin/env bash
# One-time bootstrap for the Terraform state bucket declared in backend.tf.
#
# Chicken-and-egg: the backend has to exist before `terraform init` can use it, so this
# one bucket is created with the AWS CLI rather than Terraform. Everything else in this
# project is Terraform-managed.
#
# Safe to re-run - every step is idempotent.
#
# Cost: a few KB of S3 storage. Effectively $0.
set -euo pipefail

cd "$(dirname "$0")"

set -a
source ../.env
set +a

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="cyvora-tfstate-${ACCOUNT_ID}"

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "State bucket $BUCKET already exists."
else
  echo "Creating state bucket $BUCKET in $REGION..."
  # us-east-1 is the one region that rejects a LocationConstraint.
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION"
  fi
fi

# Versioning: state corruption or a bad apply is recoverable by rolling back to a
# previous object version.
aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

# State holds the feed API keys (they're Lambda env vars). Encrypt at rest and make sure
# nothing about this bucket can ever be public.
aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'

aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Old state versions pile up on every apply. 90 days is plenty of rollback history.
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$BUCKET" \
  --lifecycle-configuration \
  '{"Rules":[{"ID":"expire-old-state-versions","Status":"Enabled","Filter":{},"NoncurrentVersionExpiration":{"NoncurrentDays":90}}]}'

echo
echo "State bucket ready: s3://$BUCKET"
echo "Confirm infra/backend.tf's bucket matches, then run:"
echo "  ./run.sh init -migrate-state"
