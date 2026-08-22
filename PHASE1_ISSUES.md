# Phase 1 — Blocking Issues & Cost Audit

Generated 2026-07-28, verified against the live stack on 2026-08-22. **Every issue below
is now closed**, including both external blockers. The document is kept as the record of
what each decision cost and why it was made - the reasoning is the point, not the status.

Constraint driving this list: **the project must run at effectively $0/month.** Anything
outside AWS "always free" allowances, or anything with unbounded growth, is treated as a
blocker even if it's only cents today.

Status legend: `[ ]` open · `[x]` fixed

**Update 2026-08-22:** the stack is fully applied — 72 managed resources, up from the 61
of v1, with v2's OTX feed, anomaly detector and alerts table added since. Measured live
today: 81 Lambda invocations/day, 23,520 IOCs in `cyvora-iocs` (5.7 MB), 229 objects in
the landing bucket (63.6 MB, held flat by the 7-day expiry). No throttled writes. Actual
spend remains $0 against the $5 budget alarm.

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

**Follow-up (v2):** that 25/25 is **account-wide, not per-table** — a detail worth stating
plainly, because it means the pool is now 24/25 spoken for and a second provisioned table
does not fit. When v2 needed an alerts table, it went `PAY_PER_REQUEST` for exactly that
reason: on-demand has no free allowance, but a handful of alert rows a day rounds to
fractions of a cent, whereas there was simply no provisioned capacity left to allocate.
The same constraint is why per-feed state and the anomaly counters live in S3.

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
### D5 — README missing architecture diagram + screenshots [x]
DoD item, was blocked on D1/D2 (needed a live URL to screenshot). The diagram now covers
all four feeds and the anomaly branch; screenshots are in `docs/images/`.

### D6 — CloudWatch dashboards [x]
Guide line 63 asks for dashboards + alarms. Alarms exist in `infra/cloudwatch.tf` (6 of the
10 always-free alarms). Dashboards: the first 3 are always-free.

---

## Cost projection after all fixes

Measured 2026-08-22 against the live stack, rather than projected.

| Service | Measured usage | Cost |
|---|---|---|
| Lambda | 81 invocations/day across 8 functions | $0 (1M/mo always free) |
| DynamoDB `cyvora-iocs` | 23,520 items, 5.7 MB, 24 WCU / 25 RCU provisioned | $0 |
| DynamoDB `cyvora-alerts` | on-demand, a handful of rows/day | <$0.01 |
| S3 landing | 229 objects, 63.6 MB, flat under the 7-day expiry | ~$0.01 |
| S3 frontend | <10 MB | ~$0.00 |
| CloudFront | portfolio traffic | $0 (1 TB/mo always free) |
| CloudWatch | 9 alarms, 1 dashboard, 7-day log retention | $0 |
| SNS | a few emails/mo | $0 (1,000/mo free) |
| API Gateway | portfolio traffic | ~$0.01 |

Budget alarm stays at $5/month as the backstop, and has never fired.

Two ceilings are now close enough to matter when extending this: DynamoDB's always-free
25 WCU / 25 RCU is **account-wide** and 24/25 is in use, and 9 of CloudWatch's 10 free
alarms are in use — so one more Lambda fits, and a second provisioned table does not.

---

## External blockers — both resolved

Neither was a code or configuration problem; both needed a human with console access.

### X1 — CloudFront blocked pending AWS account verification [x]

The first apply created 60 of 61 resources. The distribution failed with:

```
AccessDenied: Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

A standard restriction on brand-new accounts (this one was created 2026-07-27), not
something Terraform could work around. Cleared through a free Basic-support case, after
which `infra/cloudfront.tf` applied unchanged. The site has been live since.

### X2 — First pipeline run not yet observed [x]

Confirmed running end to end. `cyvora-iocs` holds 23,520 IOCs, `GET /iocs?type=ip&geo=true`
returns 100 geo-tagged points, and both the globe and 2D map render them. The suite that
was 20 tests at the time of writing is now 111 (68 ingestion, 22 backend, 21 frontend).

Verification commands are at the end of `EXECUTION_GUIDE.md`'s progress log.
