# Schedules the 4 ingestion Lambdas and wires the landing bucket to auto-invoke the
# normalizer on every new object.

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_invoke" {
  name               = "${var.project_name}-scheduler-invoke"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
}

data "aws_iam_policy_document" "scheduler_invoke_lambda" {
  statement {
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.urlhaus.arn,
      aws_lambda_function.feodo.arn,
      aws_lambda_function.cisa_kev.arn,
      aws_lambda_function.abuseipdb_enrich.arn,
      aws_lambda_function.anomaly_detector.arn,
    ]
  }
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  name   = "${var.project_name}-scheduler-invoke-lambda"
  role   = aws_iam_role.scheduler_invoke.id
  policy = data.aws_iam_policy_document.scheduler_invoke_lambda.json
}

# abuse.ch regenerates URLhaus/Feodo dumps every 5 minutes, but polling that fast buys
# nothing here and costs a lot: /urls/recent/ returns the same rolling ~550 URLs every
# time, so 288 pulls/day meant ~160k DynamoDB writes/day for a few dozen genuinely new
# records. Hourly, combined with the watermark in ingestion/normalizer/handler.py, keeps
# the whole pipeline inside the free tier. The feed window is far wider than an hour, so
# nothing is missed.
resource "aws_scheduler_schedule" "urlhaus" {
  name       = "${var.project_name}-urlhaus"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 hour)"

  target {
    arn      = aws_lambda_function.urlhaus.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

resource "aws_scheduler_schedule" "feodo" {
  name       = "${var.project_name}-feodo"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 hour)"

  target {
    arn      = aws_lambda_function.feodo.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

# CISA adds entries irregularly, a few times/week - daily polling is sufficient.
resource "aws_scheduler_schedule" "cisa_kev" {
  name       = "${var.project_name}-cisa-kev"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 day)"

  target {
    arn      = aws_lambda_function.cisa_kev.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

# AbuseIPDB free tier is 1,000 checks/day - daily keeps this nowhere near quota even
# once _get_unenriched_ips is wired up to a real batch.
resource "aws_scheduler_schedule" "abuseipdb_enrich" {
  name       = "${var.project_name}-abuseipdb-enrich"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 day)"

  target {
    arn      = aws_lambda_function.abuseipdb_enrich.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

# Runs once daily, after normalizer has had the whole day to accumulate counts in
# _state/anomaly_counts.json (see ingestion/anomaly_detector/handler.py).
resource "aws_scheduler_schedule" "anomaly_detector" {
  name       = "${var.project_name}-anomaly-detector"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 day)"

  target {
    arn      = aws_lambda_function.anomaly_detector.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

# One notification per feed prefix rather than a bucket-wide rule. The normalizer also
# writes its own watermark objects under _state/ (see ingestion/common/feed_state.py),
# and a bucket-wide rule would have those re-invoke the normalizer on every run - a
# pointless invocation each time, and one bad parser change away from a write loop.
resource "aws_s3_bucket_notification" "landing_triggers_normalizer" {
  bucket = aws_s3_bucket.landing.id

  dynamic "lambda_function" {
    for_each = toset(["urlhaus/", "feodo/", "cisa_kev/"])

    content {
      lambda_function_arn = aws_lambda_function.normalizer.arn
      events              = ["s3:ObjectCreated:*"]
      filter_prefix       = lambda_function.value
    }
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_normalizer]
}
