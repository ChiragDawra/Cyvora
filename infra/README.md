# infra

Terraform for every AWS resource Cyvora uses — **72 managed resources, all applied and
live.** The only thing here that Terraform does not manage is the state bucket itself,
created by `bootstrap.sh`, because a backend cannot provision itself.

## What's defined

| File | Contents |
|---|---|
| `versions.tf`, `providers.tf`, `variables.tf` | provider pins and input variables |
| `backend.tf` | S3 remote state with native lockfile locking (`use_lockfile`) — no DynamoDB lock table, so no extra cost |
| `s3.tf` | landing bucket (raw feed pulls, 7-day expiry) and frontend bucket — both private, no public access |
| `dynamodb.tf` | `cyvora-iocs` (provisioned, `type-time-index` GSI, 90-day TTL) and `cyvora-alerts` (on-demand, 30-day TTL) |
| `lambda.tf` | 8 functions — urlhaus, feodo, cisa_kev, otx, abuseipdb_enrich, normalizer, anomaly_detector, api — plus the shared dependency layer |
| `eventbridge.tf` | 6 schedules (urlhaus/feodo hourly; cisa_kev, otx, abuseipdb_enrich, anomaly_detector daily) and the S3-to-normalizer trigger |
| `apigateway.tf` | HTTP API in front of the `api` Lambda: `GET /iocs`, `GET /iocs/{ioc_id}`, `GET /alerts` |
| `cloudfront.tf` | CDN in front of the frontend bucket, OAC-secured so the bucket stays private — this is what gives the project its public URL |
| `cloudwatch.tf` | one dashboard, one error alarm per Lambda plus a DynamoDB throttle alarm (9 total), 7-day log retention, and the SNS alerts topic |
| `iam.tf` | shared Lambda execution role, scoped to the landing bucket, the two tables and the SNS topic — not account-wide |
| `github_oidc.tf` | the role GitHub Actions assumes to deploy, so no long-lived AWS keys exist in the repo |
| `budgets.tf` | $5/month cost alarm at 80% actual and 100% forecasted |
| `outputs.tf` | `api_url`, `cloudfront_domain`, `cloudfront_distribution_id`, bucket and role names |

Two capacity ceilings shape several of these choices and are worth knowing before
changing anything:

- **DynamoDB's always-free 25 WCU / 25 RCU is account-wide, not per-table.** `cyvora-iocs`
  holds 24 of 25 WCU and all 25 RCU. That is why `cyvora-alerts` is on-demand — there was
  no provisioned capacity left to give it — and why per-feed state lives in S3 rather than
  in a table. A new provisioned table will not fit.
- **CloudWatch's always-free tier is 10 alarms.** 9 are in use, so exactly one more Lambda
  can be added before alarms start costing money.

## First-time setup

1. Create `.env` in the repo root from `.env.example` and fill in the AWS credentials and
   feed API keys. It is gitignored.
2. Copy `terraform.tfvars.example` to `terraform.tfvars` and set `budget_alert_email`.
   Also gitignored.
3. Create the state bucket — one time, idempotent, safe to re-run:
   ```
   ./bootstrap.sh
   ```
4. Build the Lambda layer. `lambda.tf`'s `archive_file` reads the directory it produces,
   so without this the plan fails with "could not archive missing directory":
   ```
   ../ingestion/build_layer.sh
   ```
5. Use `./run.sh` rather than calling `terraform` directly — it sources `../.env` and maps
   `ABUSECH_AUTH_KEY`, `ABUSEIPDB_API_KEY` and `OTX_API_KEY` to the `TF_VAR_*` names the
   Lambda environment variables expect:
   ```
   ./run.sh plan
   ./run.sh apply
   ```

## Deploying

Pushing to `main` deploys: CI runs, and on success `.github/workflows/deploy.yml` applies
this stack and publishes the frontend, authenticating through GitHub OIDC. That workflow
needs `AWS_ROLE_ARN` as a repository variable and `ABUSECH_AUTH_KEY`, `ABUSEIPDB_API_KEY`,
`OTX_API_KEY` and `BUDGET_ALERT_EMAIL` as repository secrets.

Every variable without a default in `variables.tf` must be passed by that workflow, or the
apply fails outright rather than degrading. `scripts/check_deploy_vars.py` enforces that in
CI — it exists because `otx_api_key` was once missed, which broke automatic deploys while
going unnoticed, since the feed had been applied by hand from a local shell.

To deploy from your machine instead, `./run.sh apply` then `../scripts/deploy_frontend.sh`.
Do not sync the frontend by hand: the API URL is baked in at build time (`next.config.ts`
sets `output: "export"`, and Next.js inlines `NEXT_PUBLIC_*` during the build), so the
order must always be apply, read outputs, build, sync, invalidate. The script does that in
the right order and the deploy workflow inlines the same steps.

## Notes on deliberate limitations

- **Geo coverage is partial on purpose.** Only Feodo IOCs (which carry a `country` field)
  and AbuseIPDB-enriched IPs get plotted. URLhaus URLs and CISA KEV CVEs have no inherent
  geography and are not force-mapped — see `ingestion/common/geo.py` and the
  attribution reframe in `EXECUTION_GUIDE.md`.
- **`abuseipdb_enrich` scans with a filter** rather than querying an index, because no GSI
  can express "missing an attribute". Fine at this scale; revisit if the table grows.
- **The geo GSI is still deferred.** It needs a geohash scheme — DynamoDB has no native
  geospatial index — and there is no spare provisioned capacity for one anyway.
