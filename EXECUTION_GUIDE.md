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

---

## Phase 0 — Repo & environment setup

Do this before writing any feature code.

- [ ] Confirm `.gitignore` is in place (see this repo's `.gitignore`) and stop tracking `.DS_Store`
- [ ] Choose runtimes: **Python** for ingestion/normalization Lambdas and any ML code, **Node.js + React/Next.js** for the frontend
- [ ] Create an AWS account (or confirm you have one) and set a **AWS Budgets alarm** immediately — before provisioning anything else
- [ ] Decide secrets handling: local `.env` (gitignored) for dev, **AWS SSM Parameter Store or Secrets Manager** for deployed Lambdas
- [ ] Pick IaC tool: **Terraform** (see "Open assumptions" below if you'd rather use CDK/CloudFormation)
- [ ] Scaffold repo folders: `/infra` (Terraform), `/ingestion` (feed-pull Lambdas), `/backend` (API Lambda), `/frontend` (React/Next.js app)
- [ ] Set up GitHub Actions CI skeleton (lint/test on push, deploy on merge to main) — can be a no-op pipeline initially, filled in during Phase 1

## Phase 1 — v1 MVP (the freeze target)

**No ML in this phase.** Goal: a live, deployed, IaC-managed pipeline showing real threat data on a map.

### Feeds (exactly these 3 — do not add more in v1)
- [ ] Register an **abuse.ch Auth-Key** (mandatory since June 2025) and pull **URLhaus** + **Feodo Tracker**
- [ ] Integrate **CISA KEV** feed (free, no key, no auth — highest-value/lowest-friction feed, do this one first)
- [ ] Register an **AbuseIPDB** free-tier key (1,000 checks/day) and use it to enrich a *filtered subset* of IOCs only — never bulk-enrich through a rate-limited endpoint

### Ingestion & storage
- [ ] One **EventBridge Scheduler → Lambda (Python)** per feed, matched to that feed's update cadence
- [ ] Raw pulls land in **S3**; a normalization Lambda maps each feed's format into one common IOC schema
- [ ] **DynamoDB** as the current IOC/alert store, with GSIs on time and geo (stays inside the always-free 25GB tier)
- [ ] S3 + Athena for historical/append-only records (skip AWS Timestream — closed to new customers since June 2025; use Timestream for InfluxDB or Postgres/RDS if you need real time-series queries later)

### Backend & frontend
- [ ] **API Gateway + Lambda** backend serving IOC/alert data
- [ ] **React/Next.js** frontend, globe view via **globe.gl / react-globe.gl**, with a **2D map fallback (Leaflet or deck.gl)**
- [ ] Deploy frontend via **S3 + CloudFront**

### Infra & ops
- [ ] All infra defined in **Terraform**, applied via CI
- [ ] **GitHub Actions** CI/CD: lint/test → terraform plan → terraform apply on merge
- [ ] **CloudWatch** dashboards + alarms for Lambda errors/latency
- [ ] Confirm the **AWS Budgets alarm** from Phase 0 is actually active

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
