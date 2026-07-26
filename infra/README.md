# infra

Terraform for Cyvora's AWS resources.

## What's actually defined so far
- `versions.tf` / `providers.tf` / `variables.tf` — provider + input variable scaffolding
- `s3.tf` — landing bucket (raw feed pulls) and frontend hosting bucket
- `dynamodb.tf` — the IOC/alert store (`type-time-index` GSI for querying by feed type + recency)
- `budgets.tf` — AWS Budgets cost alarm (80% actual, 100% forecasted) — **apply this one first**
- `outputs.tf`

## Deliberately not yet defined
Lambda functions, EventBridge Scheduler rules, API Gateway, and CloudFront are **not** in this skeleton yet. Writing them now would produce Terraform that references Lambda deployment packages that don't exist — the ingestion/backend Python code in `../ingestion` and `../backend` has no build/packaging pipeline (dependency vendoring, zip/layer creation) set up yet. Add these resources feed-by-feed as each Lambda is actually built and its packaging is worked out, per `../EXECUTION_GUIDE.md` Phase 1.

## Before running `terraform plan`
- `terraform` and the `aws` CLI are not installed in this dev environment — install both and run `aws configure` (or set up SSO) first
- Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in `budget_alert_email` (gitignored, never commit real values)
- None of this has been run against real AWS yet — treat it as unvalidated until a `terraform plan` succeeds
