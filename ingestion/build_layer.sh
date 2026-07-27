#!/usr/bin/env bash
# Builds the Lambda layer directory: pip-installs `requests` (and its transitive deps)
# as Linux/Lambda-compatible wheels regardless of the host OS/arch, plus the shared
# common/ package. boto3 is NOT bundled - it already ships in the Lambda Python
# runtime. Run this before `terraform apply` in infra/ (or from infra/lambda.tf's
# null_resource, which calls this automatically).
set -euo pipefail

cd "$(dirname "$0")"

LAYER_DIR="build/layer/python"
rm -rf build
mkdir -p "$LAYER_DIR"

pip3 install \
  --platform manylinux2014_x86_64 \
  --target "$LAYER_DIR" \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all: \
  --upgrade \
  requests

cp -r common "$LAYER_DIR/common"
find "$LAYER_DIR/common" -name "__pycache__" -type d -exec rm -rf {} +

echo "Layer built at $LAYER_DIR"
