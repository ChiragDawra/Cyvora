# Cyvora — Execution Guide

This is the single live source of truth for building Cyvora. `GPT_Analysis.md` and `Claude_Analysis.md` are kept as historical/reference material only — where they conflict, **this file's decisions win**.

## Decisions locked in

- **Product name:** Cyvora (the docs called it "ThreatMap" — that name is retired).
- **Source of truth for scope:** `Claude_Analysis.md`'s staged MVP plan. `GPT_Analysis.md` is background reference only (feed comparison table, ML technique overview, viz library trade-offs) — its team-size and "all 7 feeds / all 5 ML techniques" scope is **not** the plan.
- **Team size:** Solo build.
- **Timeline:** Tight deadline (job/placement search). **v1 is the real target — ship and polish it.** v2 and v3 are optional stretch goals, not commitments. If crunched for time, freeze at v1.
- **Positioning:** Cloud/DevOps engineering is the headline skill this project demonstrates. ML is a secondary, honestly-scoped layer — never oversell "prediction" or "attacker origin attribution."

## How to use this guide

Check off tasks as you finish them. Don't skip ahead to v2/v3 until v1's Definition of Done is fully checked. When in doubt about a decision, this file's "Open assumptions" section below tells you what's been assumed on your behalf and can still be changed before you start.

## Progress log

- **2026-07-26:** Phase 0 repo scaffolding done — folder structure, Python Lambda stubs (ingestion + backend, untested against real feeds/AWS), Next.js frontend (builds clean, placeholder data only), Terraform skeleton (S3 + DynamoDB + Budgets alarm defined but **not applied** — no AWS account/credentials configured in this environment), GitHub Actions CI skeleton (lint/build/`terraform validate`, no deploy job yet). **Nothing is deployed. No feed API keys are registered yet.** Phase 1's actual checklist items below are still open — see each item's TODO comments in the corresponding source file for exactly what's stubbed vs. real.
- **2026-07-26 (later):** Verified CISA KEV and Feodo Tracker field names against live feed responses and fixed a real bug in the normalizer (Feodo's last-seen field is `last_online`, not `last_seen` — the code previously silently produced empty strings for every record). Added a pytest suite (`ingestion/tests/`, 8 tests, all passing) covering the schema and all three parsers, wired into CI. URLhaus's response wrapper is still unconfirmed — no Auth-Key exists yet to test against the live endpoint. **Still blocked on the same things:** AWS account, abuse.ch Auth-Key, AbuseIPDB key — none of this is deployed or connected to a real feed yet.
- **2026-07-27:** Real abuse.ch Auth-Key and AbuseIPDB key registered and placed in a gitignored `.env` (fixed to the `ABUSECH_AUTH_KEY`/`ABUSEIPDB_API_KEY` names the code actually reads — the first draft used non-standard key names/format that wouldn't have loaded). Hit all 3 v1 feeds live: URLhaus's `{"query_status": ..., "urls": [...]}` wrapper is now **confirmed correct**, but that endpoint has no `last_online` field at all (only `date_added`) — fixed the normalizer, which had guessed a fallback for a field that doesn't exist there. Feodo and AbuseIPDB responses matched what was already coded, no changes needed. Also validated `_parse_cisa_kev` against the full real catalog (1,653 entries, 0 parse failures) using a local download. **Still blocked on:** AWS account/credentials — nothing is deployed yet; the feed *logic* is now proven against live data, but no Lambda, EventBridge schedule, or DynamoDB write has actually run.
- **2026-07-27 (later):** AWS account created, IAM user `Cyvora-Terraform` set up with `AdministratorAccess` (not root — good), keys added to `.env`, confirmed working via `aws sts get-caller-identity`. Installed Terraform + AWS CLI locally (`brew install awscli` + `brew install hashicorp/tap/terraform` — plain `brew install terraform` no longer works, HashiCorp pulled it from homebrew-core). `terraform init`/`fmt`/`validate` all pass for the first time against the real provider. **First real AWS resource is live:** the Budgets alarm (`aws_budgets_budget.monthly`) — $5/month, 80% actual + 100% forecasted email alerts, verified via `aws budgets describe-budget` (status `HEALTHY`, `$0` spend so far). Note: the harness's own auto-mode classifier blocks `terraform apply` from running unattended, so applies need to be run by the user directly (interactively, with the `yes` prompt) rather than by me with `-auto-approve` — that's how this one landed. Same approach will apply to every subsequent `terraform apply` in this project.

---

## Phase 0 — Repo & environment setup

Do this before writing any feature code.

- [x] Confirm `.gitignore` is in place and stop tracking `.DS_Store`
- [x] Choose runtimes: **Python** for ingestion/normalization Lambdas and any ML code, **Node.js + React/Next.js** for the frontend
- [x] Create an AWS account (or confirm you have one) and set a **AWS Budgets alarm** immediately — before provisioning anything else *(done — account + IAM user set up, Terraform + AWS CLI installed locally, `aws_budgets_budget.monthly` applied and confirmed live: $5/month, HEALTHY)*
- [x] Decide secrets handling: local `.env` (gitignored) for dev — `.env` now has real `ABUSECH_AUTH_KEY`/`ABUSEIPDB_API_KEY`/`OTX_API_KEY` (confirmed gitignored, confirmed working). **AWS SSM Parameter Store or Secrets Manager** for deployed Lambdas is still just a decision, nothing wired up — no AWS account yet
- [x] Pick IaC tool: **Terraform** (see "Open assumptions" below if you'd rather use CDK/CloudFormation)
- [x] Scaffold repo folders: `/infra` (Terraform), `/ingestion` (feed-pull Lambdas), `/backend` (API Lambda), `/frontend` (React/Next.js app)
- [x] Set up GitHub Actions CI skeleton (lint/build/`terraform validate` on push — no deploy job yet, that needs Phase 1's Lambda packaging + AWS OIDC role first)

## Phase 1 — v1 MVP (the freeze target)

**No ML in this phase.** Goal: a live, deployed, IaC-managed pipeline showing real threat data on a map.

### Feeds (exactly these 3 — do not add more in v1)
- [x] Register an **abuse.ch Auth-Key** (mandatory since June 2025) *(done — key in `.env`, confirmed working live against both URLhaus and Feodo)*
- [ ] Pull **URLhaus** + **Feodo Tracker** into the actual pipeline *(fetch logic confirmed live and correct; `write_raw()`'s S3 write is still untested — no AWS bucket exists yet)*
- [x] Integrate **CISA KEV** feed (free, no key, no auth) *(parser validated against the full real catalog, 1,653/1,653 entries — highest-confidence feed of the three; still not actually deployed/scheduled)*
- [x] Register an **AbuseIPDB** free-tier key (1,000 checks/day) *(done — key in `.env`, confirmed working live)*
- [ ] Use AbuseIPDB to enrich a *filtered subset* of IOCs only — never bulk-enrich through a rate-limited endpoint *(single live test call confirmed the API contract; `_get_unenriched_ips` in `ingestion/abuseipdb_enrich/handler.py` is still a placeholder — no real DynamoDB query wired up since there's no table yet)*

### Ingestion & storage
- [ ] One **EventBridge Scheduler → Lambda (Python)** per feed, matched to that feed's update cadence *(Lambda code written, no EventBridge schedule or actual deployment yet — that's Terraform work still to add per `infra/README.md`)*
- [x] Raw pulls land in **S3**; a normalization Lambda maps each feed's format into one common IOC schema *(`ingestion/normalizer/handler.py` — all three parsers now verified against live, authenticated feed responses, including the full 1,653-entry real KEV catalog. Fixed a real URLhaus bug: that endpoint has no `last_online` field at all, unlike Feodo. Covered by 9 passing tests in `ingestion/tests/`. The S3-write and DynamoDB-write halves of the pipeline are still untested — no AWS account yet)*
- [ ] **DynamoDB** as the current IOC/alert store, with GSIs on time and geo (stays inside the always-free 25GB tier) *(table + time GSI defined in `infra/dynamodb.tf`, not yet applied; geo GSI deferred — needs a geohash scheme, not a native DynamoDB feature)*
- [ ] S3 + Athena for historical/append-only records (skip AWS Timestream — closed to new customers since June 2025; use Timestream for InfluxDB or Postgres/RDS if you need real time-series queries later)

### Backend & frontend
- [ ] **API Gateway + Lambda** backend serving IOC/alert data *(`backend/api/handler.py` stubbed, uses a full table `scan` until the GSI-based query TODO is done — not deployed)*
- [x] **React/Next.js** frontend, globe view via **globe.gl / react-globe.gl**, with a **2D map fallback (Leaflet)** — scaffolded and builds clean (`npm run build` passes) with placeholder points; not yet wired to the real API
- [ ] Deploy frontend via **S3 + CloudFront**

### Infra & ops
- [ ] All infra defined in **Terraform**, applied via CI *(Budgets alarm applied and live; S3/DynamoDB defined but not yet applied — Lambda/API Gateway/EventBridge/CloudFront still to add. Applies must be run by the user directly — the harness blocks `terraform apply -auto-approve` from running unattended)*
- [x] **GitHub Actions** CI/CD: lint/build/`terraform validate` wired up (`.github/workflows/ci.yml`) — `terraform apply`/deploy step still to add once there's something real to deploy
- [ ] **CloudWatch** dashboards + alarms for Lambda errors/latency
- [x] Confirm the **AWS Budgets alarm** from Phase 0 is actually active *(confirmed via `aws budgets describe-budget`: status HEALTHY, $5/month limit, $0 spend so far)*

### Definition of Done (v1)
- [ ] All 3 feeds ingesting on schedule with visible, correctly-plotted data on the map
- [ ] 100% of infra provisioned through Terraform + CI/CD (no manual console changes)
- [ ] Publicly reachable URL (CloudFront), budget alarm confirmed active
- [ ] README updated with architecture diagram/summary + screenshots
- [ ] No feature, copy, or label anywhere claims "prediction" or "attacker origin" — see Explicitly Out of Scope below

---

## Phase 2 — v2 (optional stretch, only after v1 is fully done)

- [ ] Statistical anomaly detection on per-category feed volume (PyOD or Prophet — not a from-scratch model)
- [ ] SNS-based spike alerts (email or webhook) wired to the anomaly detector
- [ ] DBSCAN or K-means clustering view over IOC attributes
- [ ] Add **AlienVault OTX** feed for MITRE ATT&CK / target-industry context (requires a free key + subscribing to ≥1 pulse)

## Phase 3 — v3 (stretch, only if meaningfully ahead of schedule)

- [ ] Integrate **MITRE TRAM** (the open-source SciBERT-based tool) for ATT&CK tagging — reuse it, don't build a classifier from scratch. Run it containerized on ECS/Fargate.
- [ ] LSTM sequence forecasting, but only if explicitly benchmarked against ARIMA/Prophet/seasonal-naïve baselines and clearly labeled "experimental" in the UI
- [ ] User IP-range subscription/alerting (requires a basic auth model — not designed yet, see Open assumptions)

---

## Explicitly out of scope

These were in `GPT_Analysis.md`'s original scope but are deliberately dropped or reframed per `Claude_Analysis.md`'s feasibility critique:

- **Twitter OSINT, Censys, VirusTotal, MISP** feeds — not part of v1–v3
- **Shodan's paid API** — use the free, keyless **InternetDB** (`internetdb.shodan.io`) and **CVEDB** instead
- **SageMaker** — too costly/complex for this scale; run scikit-learn/PyOD/Prophet in Lambda or a small scheduled Fargate task instead
- **AWS Timestream** — closed to new customers (June 2025); use Timestream for InfluxDB or Postgres/RDS
- **"Prediction engine" framing** — reframed as anomaly *flagging*, not prediction
- **"Attacker origin attribution" via IP geolocation** — technically unsound (VPNs/proxies/botnets/spoofing defeat it; see CISA Alert AA20-198A). Reframe as "geolocation of malicious infrastructure/exit nodes," never "where the attacker is"

## Positioning (resume & interviews)

- Lead with the **cloud/DevOps engineering** work: Terraform-managed infra, CI/CD, multi-Lambda event-driven pipeline, cost-aware architecture (free-tier-conscious, budget alarms).
- Frame ML as a secondary, honestly-scoped layer — statistical anomaly detection and clustering, not a black-box "AI predicts attacks" claim.
- Differentiate from "attack maps are theater" criticism (the 2016 Norse Corp debunking) by being transparent about data sources, citing real feeds, and labeling anything experimental as experimental.
- Be ready to answer: "How do you know the attack really came from that country?" — answer honestly using the geolocation-of-infrastructure reframe above, not an origin-attribution claim.

## Open assumptions (flagged for override before Phase 0)

These are recommendations carried over from `Claude_Analysis.md`, not hard requirements:

- **IaC tool: Terraform** — swap for CDK or CloudFormation if you prefer.
- **Frontend: React/Next.js + globe.gl** — swap for another stack if you have a strong preference.
- **Auth model for v3's user subscriptions** — not yet designed; will need a decision if/when v3 is reached.
