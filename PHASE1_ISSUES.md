# Phase 1 — Blocking Issues & Cost Audit

Generated 2026-07-28. Everything in `EXECUTION_GUIDE.md` Phase 1 that is still open,
plus every place the current Terraform would cost real money if applied as-is.

Constraint driving this list: **the project must run at effectively $0/month.** Anything
outside AWS "always free" allowances, or anything with unbounded growth, is treated as a
blocker even if it's only cents today.

Status legend: `[ ]` open · `[x]` fixed

**Update 2026-07-28:** every issue below is fixed and applied except where noted.
`terraform apply` created 60 of 61 resources. The one failure is **not a config problem** —
see "Remaining external blockers" at the bottom.

---

## A. Cost blockers (would spend money if `terraform apply` ran today)

### A1 — URLhaus write amplification [x]
`infra/eventbridge.tf` polls URLhaus every 5 min. `ingestion/normalizer/handler.py`
re-writes **every** record in every pull, unconditionally.

Measured live (2026-07-28): URLhaus `/v1/urls/recent/` = 364 KB, **558 URLs**.

- 288 pulls/day x 558 items = **160,704 DynamoDB writes/day** = ~4.8M writes/month
- With `projection_type = "ALL"` on the GSI, every write is billed twice = ~9.6M WRU/mo
- On-demand at $1.25/M WRU = **~$12/month** — over the $5 budget alarm on its own

The data barely changes between pulls: the same 558 URLs get rewritten 288 times/day.

**Fix:** watermark the feed (only write records newer than the last-seen `date_added`),
and drop URLhaus/Feodo cadence from 5 min to hourly. Steady state drops to a few hundred
writes/day.

### A2 — GSI projects ALL attributes [x]
`infra/dynamodb.tf`, `type-time-index` uses `projection_type = "ALL"`, which doubles both
write cost and stored bytes (the `raw` blob gets copied into the index). The API only reads
a handful of fields off the index.

**Fix:** `projection_type = "INCLUDE"` with just the attributes `backend/api/handler.py`
and the map actually render.

### A3 — No S3 lifecycle rule on the landing bucket [x]
`infra/s3.tf` has no expiration. At 288 pulls/day x 364 KB that's ~3 GB/month accumulating
forever, and the 5 GB S3 free allowance is a 12-month offer, not always-free.

**Fix:** lifecycle rule expiring landing objects after 7 days + abort incomplete multipart
uploads.

### A4 — No CloudWatch Logs retention [x]
Lambda auto-creates its log groups with **retention = Never Expire**, and those groups
aren't Terraform-managed at all (so they also survive `terraform destroy`, violating the
"100% infra in Terraform" DoD item).

**Fix:** declare one `aws_cloudwatch_log_group` per function with
`retention_in_days = 7`.

### A5 — No TTL on the IOC table [x]
DynamoDB's always-free 25 GB is the only thing keeping storage at $0. Nothing expires old
IOCs, so the table grows without bound.

**Fix:** enable TTL on an `expires_at` attribute; set it in `IOC.to_dynamo_item()`.

### A6 — DynamoDB capacity mode [x]
`PAY_PER_REQUEST` has **no** always-free allowance. The always-free DynamoDB tier is
25 GB storage + 25 WCU + 25 RCU, and only applies to **provisioned** mode.

**Fix:** decision required — provisioned (guaranteed $0, throttles under burst) vs.
on-demand (simpler, ~$0.05/mo once A1/A2 are fixed).


**Resolved:** provisioned. Table 12 WCU / 5 RCU, GSI 12 WCU / 20 RCU — 24 WCU and
25 RCU total, inside the always-free 25/25.

### A7 — API Gateway has no always-free tier [x]
HTTP API is $1.00/M requests after the 12-month free window. At portfolio traffic this is
cents, but a Lambda Function URL does the same job for exactly $0.

**Fix:** decision required — keep API Gateway (better resume artifact, ~$0.01/mo) or swap
to a Function URL.


**Resolved:** kept API Gateway. ~$0.01/month at portfolio traffic, and it's the stronger
resume artifact. A `dynamodb_throttles` alarm and the $5 budget alarm bound the downside.

---

## B. Apply blockers (`terraform apply` fails or misbehaves)

### B1 — S3 bucket names are not globally unique [x]
`cyvora-landing` and `cyvora-frontend` are bare names in a global namespace. High chance of
`BucketAlreadyExists` on first apply.

**Fix:** suffix both with the AWS account ID via `data.aws_caller_identity`.

### B2 — `aws_lambda_permission` missing `source_account` [x]
The S3-invoke permission on the normalizer is scoped by bucket ARN only. Bucket ARNs
contain no account ID, so a cross-account confused-deputy path exists.

**Fix:** add `source_account = data.aws_caller_identity.current.account_id`.

### B3 — CloudFront uses the legacy `forwarded_values` block [x]
Deprecated in AWS provider v5; also means no compression and no managed cache policy.

**Fix:** switch to `cache_policy_id` (AWS managed `CachingOptimized`) + `compress = true`.

### B4 — No remote Terraform state [x]
State is local-only and gitignored. CI can never run `terraform apply` without it, which
blocks the "provisioned through CI/CD" DoD item. The one live resource
(`aws_budgets_budget.monthly`) exists only in the local state file.

**Fix:** S3 backend with native state locking (`use_lockfile = true` — no DynamoDB lock
table needed, so no extra cost), created via a one-time bootstrap.

---

## C. Correctness / product blockers

### C1 — `_get_unenriched_ips` returns nothing [x]
`ingestion/abuseipdb_enrich/handler.py` passes `Limit=MAX_IPS_PER_RUN` **and** a
`FilterExpression`. DynamoDB applies `Limit` to items *scanned*, before filtering — so the
scan reads 50 arbitrary items and then filters, usually returning zero enrichable IPs.

**Fix:** paginate the scan and stop once `MAX_IPS_PER_RUN` *matching* items are collected.

### C2 — The map will be almost empty [x]
Only IOCs with `geo` can be plotted. Today:
- URLhaus → `IOCType.URL`, no geo, never enriched (enricher only looks at `ioc_type == "ip"`)
- Feodo → has `country`, but the live blocklist is currently **5 entries**
- CISA KEV → CVEs, inherently no geo

Net: ~5 plottable points. Fails the DoD item "visible, correctly-plotted data on the map".

**Fix:** extract the host from each URLhaus URL; when it's a literal IP, emit an additional
`IOCType.IP` IOC so the AbuseIPDB enricher can geo-locate it. AbuseIPDB free tier is
1,000 checks/day and the enricher is daily + capped, so this stays free.

### C3 — `write_raw` lands unchanged payloads [x]
Every pull writes a new S3 object even when the feed content is byte-identical, which
re-triggers the normalizer for no reason.

**Fix:** hash the payload, skip the write when it matches the previous pull.

### C4 — Frontend build has no API URL [x]
`frontend/src/lib/api.ts` reads `NEXT_PUBLIC_API_URL`, but nothing supplies it. Next.js
inlines `NEXT_PUBLIC_*` at **build** time, so the URL must be exported before `npm run build`
in the deploy step.

**Fix:** deploy script/CI job reads the Terraform output and exports it before building.

---

## D. Remaining Phase 1 checklist items (not yet done at all)

### D1 — Nothing is deployed [x]
Only `aws_budgets_budget.monthly` exists in AWS. No Lambda, EventBridge schedule, S3
bucket, DynamoDB table, API, or CloudFront distribution has ever been applied.

### D2 — No frontend deploy path [x]
Nothing syncs `frontend/out/` to the frontend bucket or invalidates CloudFront.

### D3 — No CI deploy job [x]
`.github/workflows/ci.yml` stops at `terraform validate`. DoD requires apply via CI/CD.
Needs a GitHub OIDC provider + IAM role (both free) and remote state (B4).

### D4 — S3 + Athena for historical records [deferred]
Guide line 53. Athena is $5/TB scanned — at this data volume that rounds to $0, but it is
not always-free. Lowest-value v1 item; candidate to defer.


**Deferred to post-v1** by decision, with the reasoning recorded in EXECUTION_GUIDE.md.
### D5 — README missing architecture diagram + screenshots [ ]
DoD item, blocked on D1/D2 (need a live URL to screenshot).

### D6 — CloudWatch dashboards [x]
Guide line 63 asks for dashboards + alarms. Alarms exist in `infra/cloudwatch.tf` (6 of the
10 always-free alarms). Dashboards: the first 3 are always-free.

---

## Cost projection after all fixes

| Service | Usage after fixes | Cost |
|---|---|---|
| Lambda | ~900 invocations/day | $0 (1M/mo always free) |
| DynamoDB | <1 GB, few hundred writes/day | $0 |
| S3 landing | <100 MB (7-day expiry) | ~$0.01 |
| S3 frontend | <10 MB | ~$0.00 |
| CloudFront | portfolio traffic | $0 (1 TB/mo always free) |
| CloudWatch | 6 alarms, 7-day log retention | $0 |
| SNS | a few emails/mo | $0 (1,000/mo free) |
| API Gateway | depends on A7 decision | $0–0.01 |

Budget alarm stays at $5/month as the backstop.

---

## Remaining external blockers

Neither is a code or configuration problem. Both need a human with console/browser access.

### X1 — CloudFront is blocked pending AWS account verification

`terraform apply` created 60 of 61 resources. The distribution failed with:

```
AccessDenied: Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

This is a standard restriction on brand-new AWS accounts (this one was created 2026-07-27),
not something Terraform or the config can work around. `infra/cloudfront.tf` is correct and
will apply as-is once the account is verified.

**To clear it:** open a free Basic-support case at
https://console.aws.amazon.com/support/home#/case/create — choose *Account and billing*,
service *CloudFront*, and paste the error above. Usually cleared within a day. Then re-run
`./run.sh apply`, which will create only the distribution and the bucket policy that
depends on it.

Until then the API, the pipeline, and both buckets are fully live — only the public HTTPS
URL is missing.

### X2 — The first pipeline run hasn't been observed yet

The EventBridge schedules are live (URLhaus and Feodo hourly, CISA KEV and the AbuseIPDB
enricher daily), but no scheduled run had fired at the time of the apply, and the sandbox
this was built in blocks `aws lambda invoke`. The feed logic itself is verified against
live data and covered by 20 passing tests — what's unverified is specifically the deployed
S3-write and DynamoDB-write path.

**To confirm:** see the verification commands at the end of `EXECUTION_GUIDE.md`'s progress
log.
