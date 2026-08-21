# Shared dependency layer: requests + its transitive deps (Linux/manylinux wheels,
# built regardless of host OS/arch) plus the shared ingestion/common package.
# boto3 is NOT bundled - already ships in the Lambda Python runtime.
# Build it with ../ingestion/build_layer.sh before running `terraform apply` (or via
# ./run.sh, which does not run it automatically - run the build script yourself first).
data "archive_file" "layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../ingestion/build/layer"
  output_path = "${path.module}/../ingestion/build/layer.zip"
}

resource "aws_lambda_layer_version" "deps" {
  layer_name               = "${var.project_name}-ingestion-deps"
  filename                 = data.archive_file.layer_zip.output_path
  source_code_hash         = data.archive_file.layer_zip.output_base64sha256
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
}

locals {
  ingestion_env_common = {
    LANDING_BUCKET = aws_s3_bucket.landing.bucket
  }
}

data "archive_file" "urlhaus_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/urlhaus/handler.py"
  output_path = "${path.module}/../ingestion/build/urlhaus.zip"
}

# Every function below sets depends_on for its log group: Lambda creates
# /aws/lambda/<name> itself on first invocation with retention set to Never Expire, and
# whichever gets there first wins. Creating them in Terraform first is what makes the
# 7-day retention in infra/cloudwatch.tf actually stick.
resource "aws_lambda_function" "urlhaus" {
  function_name    = local.lambda_function_names.urlhaus
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 30
  filename         = data.archive_file.urlhaus_zip.output_path
  source_code_hash = data.archive_file.urlhaus_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = merge(local.ingestion_env_common, {
      ABUSECH_AUTH_KEY = var.abusech_auth_key
    })
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "feodo_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/feodo/handler.py"
  output_path = "${path.module}/../ingestion/build/feodo.zip"
}

resource "aws_lambda_function" "feodo" {
  function_name    = local.lambda_function_names.feodo
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 30
  filename         = data.archive_file.feodo_zip.output_path
  source_code_hash = data.archive_file.feodo_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = merge(local.ingestion_env_common, {
      ABUSECH_AUTH_KEY = var.abusech_auth_key
    })
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "cisa_kev_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/cisa_kev/handler.py"
  output_path = "${path.module}/../ingestion/build/cisa_kev.zip"
}

resource "aws_lambda_function" "cisa_kev" {
  function_name    = local.lambda_function_names.cisa_kev
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 60 # the KEV catalog is ~1.5 MB and still growing
  filename         = data.archive_file.cisa_kev_zip.output_path
  source_code_hash = data.archive_file.cisa_kev_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = local.ingestion_env_common
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "otx_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/otx/handler.py"
  output_path = "${path.module}/../ingestion/build/otx.zip"
}

resource "aws_lambda_function" "otx" {
  function_name = local.lambda_function_names.otx
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  # Up to MAX_PAGES sequential API calls, and pulses carry their indicators inline so
  # the responses are large - see ingestion/otx/handler.py. 120s was too tight: a single
  # cold-cache page can take ~35s and its retry another 45s, so one slow page could eat
  # the whole budget and the function got hard-killed mid-request, losing every page it
  # had already fetched. The handler's own TIME_RESERVE_SECONDS check is what actually
  # stops the paging; this is the outer bound it measures against, sized so a cold first
  # page doesn't cost the run its remaining pages. Only real duration is billed, so a
  # higher ceiling that is rarely reached costs nothing.
  timeout          = 240
  filename         = data.archive_file.otx_zip.output_path
  source_code_hash = data.archive_file.otx_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = merge(local.ingestion_env_common, {
      OTX_API_KEY = var.otx_api_key
    })
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "abuseipdb_enrich_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/abuseipdb_enrich/handler.py"
  output_path = "${path.module}/../ingestion/build/abuseipdb_enrich.zip"
}

resource "aws_lambda_function" "abuseipdb_enrich" {
  function_name = local.lambda_function_names.abuseipdb_enrich
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  # One sequential AbuseIPDB call per IP, up to MAX_IPS_PER_RUN (400) per run - see
  # ingestion/abuseipdb_enrich/handler.py. 600s leaves plenty of headroom.
  timeout          = 600
  filename         = data.archive_file.abuseipdb_enrich_zip.output_path
  source_code_hash = data.archive_file.abuseipdb_enrich_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      IOC_TABLE         = aws_dynamodb_table.iocs.name
      ABUSEIPDB_API_KEY = var.abuseipdb_api_key
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "normalizer_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/normalizer/handler.py"
  output_path = "${path.module}/../ingestion/build/normalizer.zip"
}

resource "aws_lambda_function" "normalizer" {
  function_name = local.lambda_function_names.normalizer
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  # The very first CISA KEV pull writes ~1,650 items against 12 provisioned WCU, and
  # batch_writer sits in a retry/backoff loop while DynamoDB throttles it. Steady-state
  # runs finish in seconds (the watermark filters nearly everything out), but the cold
  # backfill needs the headroom.
  timeout          = 300
  filename         = data.archive_file.normalizer_zip.output_path
  source_code_hash = data.archive_file.normalizer_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      IOC_TABLE = aws_dynamodb_table.iocs.name
      # Also needed for the per-feed watermark objects under _state/ (common/feed_state.py).
      LANDING_BUCKET = aws_s3_bucket.landing.bucket
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

data "archive_file" "anomaly_detector_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/anomaly_detector/handler.py"
  output_path = "${path.module}/../ingestion/build/anomaly_detector.zip"
}

resource "aws_lambda_function" "anomaly_detector" {
  function_name = local.lambda_function_names.anomaly_detector
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  timeout       = 30
  # Reads the per-type counters normalizer/handler.py already writes to S3 - stdlib
  # `statistics` only, no numpy, so this uses the same shared layer as every other
  # ingestion Lambda without needing to rebuild it.
  filename         = data.archive_file.anomaly_detector_zip.output_path
  source_code_hash = data.archive_file.anomaly_detector_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      LANDING_BUCKET   = aws_s3_bucket.landing.bucket
      ALERTS_TABLE     = aws_dynamodb_table.alerts.name
      ALERTS_TOPIC_ARN = aws_sns_topic.alerts.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_permission" "allow_s3_invoke_normalizer" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.normalizer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.landing.arn
  # S3 bucket ARNs contain no account ID, so source_arn alone doesn't pin the caller to
  # this account. source_account closes that confused-deputy gap.
  source_account = data.aws_caller_identity.current.account_id
}

data "archive_file" "api_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/api/handler.py"
  output_path = "${path.module}/../backend/build/api.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = local.lambda_function_names.api
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 15
  filename         = data.archive_file.api_zip.output_path
  source_code_hash = data.archive_file.api_zip.output_base64sha256

  environment {
    variables = {
      IOC_TABLE    = aws_dynamodb_table.iocs.name
      ALERTS_TABLE = aws_dynamodb_table.alerts.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}
