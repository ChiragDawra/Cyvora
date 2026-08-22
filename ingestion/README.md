# ingestion

One Lambda handler per feed, each on its own EventBridge Scheduler cadence. Every feed
handler pulls raw data and writes it **unmodified** to the S3 landing bucket. Normalization
into the common IOC schema happens separately, in `normalizer/`, triggered by the S3
object landing rather than called directly.

That split is deliberate. A feed handler that also normalized would have to get both jobs
right in one invocation, and a parsing bug would lose the pull that triggered it. Landing
raw first means the payload survives independently of whether anything downstream
understood it.

## Handlers

| Directory | Source | Cadence |
|---|---|---|
| `urlhaus/` | abuse.ch URLhaus (needs `ABUSECH_AUTH_KEY`) | hourly |
| `feodo/` | abuse.ch Feodo Tracker (needs `ABUSECH_AUTH_KEY`) | hourly |
| `cisa_kev/` | CISA Known Exploited Vulnerabilities catalog (no key) | daily |
| `otx/` | AlienVault OTX subscribed pulses (needs `OTX_API_KEY`) | daily |
| `abuseipdb_enrich/` | AbuseIPDB confidence score + country geo (needs `ABUSEIPDB_API_KEY`) | daily |
| `anomaly_detector/` | z-score over per-type daily volume; publishes SNS + writes `cyvora-alerts` | daily |
| `normalizer/` | maps each feed's raw format into the common IOC schema, writes DynamoDB | on S3 object landing |

`abuseipdb_enrich` is capped at 400 IPs/day against a 1,000/day free quota, and never bulk
calls — the endpoint is rate-limited and a 429 is handled as a clean stop, not a retry
storm. It is also the only thing that sets `geo`, and only on `ip` IOCs, which is why most
IOCs are not plottable and why the API has a `?geo=true` mode at all.

`anomaly_detector` is not a feed. It reads the rolling per-type counters the normalizer
writes to S3 and flags any type whose today count exceeds z = 3 against its own trailing
baseline. It needs 7 days of history before it will flag anything.

## Shared code (`common/`)

- `schema.py` — the `IOC` dataclass and `IOCType`, plus `to_dynamo_item()` (which is where
  the 90-day `expires_at` TTL gets set)
- `s3_landing.py` — `write_raw()`, which skips landing a payload byte-identical to the
  previous pull, but re-lands at least every 24 hours anyway so a normalization failure
  can't leave a feed stuck until the upstream data happens to change
- `feed_state.py` — a small JSON key-value store in S3, used for per-feed watermarks and
  the anomaly counters. It lives in S3 rather than DynamoDB because the table sits at 24/25
  WCU of the account-wide always-free ceiling and has no room for a second workload.
- `geo.py` — country-centroid lookup

Watermarks are the reason this pipeline is free rather than ~$12/month: URLhaus re-serves
the same ~550 URLs on every poll, and writing all of them every time was the single
largest cost line in the project. See `PHASE1_ISSUES.md` A1.

## Running the tests

```bash
cd ingestion
python3 -m venv .venv && ./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest -q
```

`conftest.py` puts this directory on the path the way the Lambda runtime does, so
`from common.schema import IOC` resolves in tests exactly as it does deployed.

The suite is offline and hits no AWS or feed endpoints. Two files are worth knowing about:

- `test_normalizer_real_data.py` runs the parsers against **real** downloaded payloads and
  skips itself when those files aren't present, so it never fails a clean checkout. It is
  what caught that URLhaus's endpoint has no `last_online` field at all.
- `test_otx.py` covers the retry and time-budget behaviour added after the puller started
  timing out against a cold upstream cache. See `otx/handler.py`'s docstring.

## The Lambda layer

`build_layer.sh` builds `build/layer/python/`, containing `requests` (as
`manylinux2014_x86_64` wheels, so it works regardless of the host OS) plus a copy of
`common/`. `boto3` is deliberately not bundled — it already ships in the Lambda Python
runtime, and vendoring it only risks a version skew.

Run it before `terraform apply`; `infra/lambda.tf`'s `archive_file` reads the directory it
produces, so an apply against a missing `build/` fails at plan time.
