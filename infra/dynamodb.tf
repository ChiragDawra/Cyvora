# Current IOC/alert store, written by ingestion/normalizer/handler.py and read by
# backend/api/handler.py. Matches ingestion/common/schema.py's IOC.to_dynamo_item().
#
# PROVISIONED, not PAY_PER_REQUEST, on purpose: DynamoDB's always-free tier is 25 WCU +
# 25 RCU + 25 GB, and it applies only to provisioned capacity. On-demand has no free
# allowance at all. The table and its GSI draw from the same account-wide 25/25 pool, so
# these must stay under 25 each when summed:
#
#   WCU: 12 (table) + 12 (GSI) = 24
#   RCU:  5 (table) + 20 (GSI) = 25
#
# Reads skew to the GSI because that's what the API queries; the table itself only takes
# single-item GetItem lookups. Writes are bursty (the daily CISA KEV pull is ~1,650
# items) - boto3's batch_writer retries throttled items automatically, and the normalizer
# Lambda's timeout is sized for that in infra/lambda.tf.
resource "aws_dynamodb_table" "iocs" {
  name           = "${var.project_name}-iocs"
  billing_mode   = "PROVISIONED"
  write_capacity = 12
  read_capacity  = 5
  hash_key       = "ioc_id"

  attribute {
    name = "ioc_id"
    type = "S"
  }

  attribute {
    name = "ioc_type"
    type = "S"
  }

  attribute {
    name = "ingested_at"
    type = "N"
  }

  # Keeps the table inside the always-free 25 GB without a cleanup job. Set by
  # IOC.to_dynamo_item() in ingestion/common/schema.py. TTL deletes are free - they don't
  # consume write capacity.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Lets the API/dashboard query "recent IOCs of type X" without a full table scan.
  #
  # INCLUDE, not ALL: an ALL projection copies every attribute into the index, doubling
  # both per-write cost and stored bytes. These are exactly the attributes
  # backend/api/handler.py returns and the frontend map renders - nothing more.
  global_secondary_index {
    name            = "type-time-index"
    hash_key        = "ioc_type"
    range_key       = "ingested_at"
    projection_type = "INCLUDE"
    non_key_attributes = [
      "value",
      "source_feed",
      "first_seen",
      "last_seen",
      "tags",
      "confidence",
      "geo",
    ]
    write_capacity = 12
    read_capacity  = 20
  }
}

# Spike-anomaly alerts, written by ingestion/anomaly_detector/handler.py and read by
# backend/api/handler.py's GET /alerts. Deliberately a SEPARATE table from cyvora-iocs:
# the account-wide always-free DynamoDB allowance (25 WCU + 25 RCU) is a single pool
# shared across every provisioned table, and the iocs table + its GSI already draw 24/25
# WCU and 25/25 RCU from it - there is no provisioned headroom left.
#
# PAY_PER_REQUEST here instead: volume is a handful of rows a day at most (anomaly
# detection runs once daily, most days flag nothing), so on-demand billing rounds to
# fractions of a cent - the same cost/simplicity tradeoff already made for API Gateway
# in PHASE1_ISSUES.md's A7. The $5 Budgets alarm remains the backstop.
resource "aws_dynamodb_table" "alerts" {
  name         = "${var.project_name}-alerts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "alert_id"

  attribute {
    name = "alert_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
