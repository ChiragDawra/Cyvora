# ingestion

One Lambda handler per feed, each invoked on its own EventBridge Scheduler cadence. Every handler pulls raw data and writes it, unmodified, to the S3 landing bucket — normalization into the common IOC schema happens separately in `normalizer/`.

- `urlhaus/` — abuse.ch URLhaus (requires Auth-Key)
- `feodo/` — abuse.ch Feodo Tracker (requires Auth-Key)
- `cisa_kev/` — CISA Known Exploited Vulnerabilities catalog (no key required)
- `abuseipdb_enrich/` — AbuseIPDB enrichment for a filtered subset of IOCs only (rate-limited, do not bulk-call)
- `normalizer/` — maps each feed's raw format into the common IOC schema and writes to DynamoDB
- `common/` — shared schema/types used by all handlers above
