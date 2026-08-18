# Single shared execution role for all v1 Lambdas (ingestion, normalizer, api).
# Scoped to exactly the landing bucket and IOC table - not account-wide access.
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project_name}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_data_access" {
  statement {
    sid       = "LandingBucketReadWrite"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.landing.arn}/*"]
  }

  # Without s3:ListBucket, a GetObject on a key that doesn't exist returns 403
  # AccessDenied instead of 404 NoSuchKey - which would make common/feed_state.py's
  # "no state yet" path raise on the very first run of every feed.
  statement {
    sid       = "LandingBucketList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.landing.arn]
  }

  statement {
    sid = "IocTableReadWrite"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:UpdateItem", # abuseipdb_enrich writes confidence/geo back onto existing items
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.iocs.arn,
      "${aws_dynamodb_table.iocs.arn}/index/*",
    ]
  }

  # anomaly_detector writes flagged spikes; api's GET /alerts route reads them back.
  statement {
    sid = "AlertsTableReadWrite"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.alerts.arn]
  }

  # anomaly_detector publishes spike alerts to the existing alerts topic (cloudwatch.tf) -
  # CloudWatch Alarms publish to it as a native AWS service integration and never needed
  # this, so it wasn't granted anywhere until now.
  statement {
    sid       = "PublishAlerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "lambda_data_access" {
  name   = "${var.project_name}-lambda-data-access"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_data_access.json
}
