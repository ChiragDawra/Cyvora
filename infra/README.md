# infra

Terraform for all of Cyvora's v1 AWS resources. `terraform validate` and a full
`terraform plan` (40 resources, 0 errors) have both been run against the real AWS
provider — nothing has been `apply`'d beyond the Budgets alarm yet (see below for why).

## What's defined
- `versions.tf` / `providers.tf` / `variables.tf` — provider + input variables
- `s3.tf` — landing bucket (raw feed pulls) and frontend hosting bucket (both private, no public access)
- `dynamodb.tf` — the IOC/alert store (`type-time-index` GSI, used by `backend/api/handler.py`'s queries)
- `budgets.tf` — AWS Budgets cost alarm (80% actual, 100% forecasted) — **already applied, live**
- `iam.tf` — shared Lambda execution role, scoped to just the landing bucket + IOC table (not account-wide)
- `lambda.tf` — the 6 Lambda functions (urlhaus, feodo, cisa_kev, abuseipdb_enrich, normalizer, api) + the shared dependency layer
- `eventbridge.tf` — schedules for the 4 ingestion Lambdas + the S3→normalizer trigger
- `apigateway.tf` — HTTP API in front of the `api` Lambda (`GET /iocs`, `GET /iocs/{ioc_id}`)
- `cloudfront.tf` — CDN in front of the frontend bucket (OAC-secured, bucket stays private) — this is what gives the project its public URL
- `cloudwatch.tf` — an error-rate alarm per Lambda, emailing `budget_alert_email`
- `outputs.tf`

## Before running `terraform plan`/`apply`
1. Build the Lambda dependency layer first — `lambda.tf`'s `archive_file` for the layer will fail with "could not archive missing directory" otherwise:
   ```
   ../ingestion/build_layer.sh
   ```
2. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in `budget_alert_email` (gitignored)
3. Use `./run.sh <command>` instead of calling `terraform` directly — it sources `../.env` and maps `ABUSECH_AUTH_KEY`/`ABUSEIPDB_API_KEY` to the `TF_VAR_*` names the Lambda env vars need:
   ```
   ./run.sh plan
   ./run.sh apply
   ```

## Applies must be run by you, not by the assistant
The harness blocks `terraform apply -auto-approve` from running unattended (by design — it's a real, spend-affecting AWS change). Run `./run.sh apply` yourself; it'll show the plan and prompt for `yes`.

## After a successful apply
- `terraform output` shows `api_url`, `cloudfront_domain`, and `cloudfront_distribution_id`
- Rebuild the frontend with the real API URL baked in, then sync to S3 and invalidate CloudFront:
  ```
  cd ../frontend
  NEXT_PUBLIC_API_URL=$(cd ../infra && terraform output -raw api_url) npm run build
  aws s3 sync out/ s3://cyvora-frontend --delete
  aws cloudfront create-invalidation --distribution-id $(cd ../infra && terraform output -raw cloudfront_distribution_id) --paths "/*"
  ```
- The Next.js app is statically exported (`next.config.ts`'s `output: "export"`) — there's no server, `NEXT_PUBLIC_API_URL` is baked in at build time, not read at runtime

## Known gaps / not yet automated
- No CI/CD deploy job yet — needs AWS OIDC role + GitHub repo secrets, which is a manual GitHub-side setup step, not something the assistant can do
- Geo coverage is partial by design: only Feodo Tracker IOCs (which include a `country` field directly) and AbuseIPDB-enriched IPs get plotted on the map. URLhaus URLs and CISA KEV CVEs have no inherent geography and are intentionally not force-mapped - see `ingestion/common/geo.py` and `EXECUTION_GUIDE.md`
- `abuseipdb_enrich`'s `_get_unenriched_ips` uses a DynamoDB `scan` with a filter (no GSI exists for "missing an attribute") - fine at MVP scale, revisit if the table grows large
