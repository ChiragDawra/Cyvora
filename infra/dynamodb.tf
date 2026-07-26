# Current IOC/alert store, written by ingestion/normalizer/handler.py and read by
# backend/api/handler.py. Matches ingestion/common/schema.py's IOC.to_dynamo_item().
resource "aws_dynamodb_table" "iocs" {
  name         = "${var.project_name}-iocs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ioc_id"

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

  # Lets the API/dashboard query "recent IOCs of type X" without a full table scan -
  # see the TODO in backend/api/handler.py to switch off `scan` once this exists.
  global_secondary_index {
    name            = "type-time-index"
    hash_key        = "ioc_type"
    range_key       = "ingested_at"
    projection_type = "ALL"
  }
}
