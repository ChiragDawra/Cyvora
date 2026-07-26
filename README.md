# Cyvora

A live, self-hostable open-source-threat-intel aggregation and anomaly-flagging dashboard. Ingests free OSINT feeds (abuse.ch URLhaus/Feodo Tracker, CISA KEV, AbuseIPDB), normalizes them into a common IOC schema, and visualizes them on a globe/2D map — built primarily as a cloud/DevOps engineering showcase, with statistical anomaly detection as an honestly-scoped secondary layer.

**Start here:** [`EXECUTION_GUIDE.md`](./EXECUTION_GUIDE.md) — the live, checkbox-tracked build plan. It reconciles the two research docs below into one source of truth; where they conflict, the guide wins.

- [`GPT_Analysis.md`](./GPT_Analysis.md) — original broad system-design research (reference only)
- [`Claude_Analysis.md`](./Claude_Analysis.md) — feasibility critique and the staged MVP plan the guide is built from

## Repo structure

```
infra/        Terraform (AWS resources)
ingestion/    Feed-puller + normalizer Lambdas (Python)
backend/      API Gateway + Lambda backend (Python)
frontend/     Next.js app (globe + 2D map views)
```

## Status

Pre-v1: repo scaffolding is in place (this structure, CI skeleton, Terraform skeleton for S3/DynamoDB/Budgets). No AWS resources have been deployed yet. See `EXECUTION_GUIDE.md` Phase 0/1 for what's next.
