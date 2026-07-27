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

resource "aws_lambda_function" "urlhaus" {
  function_name    = "${var.project_name}-urlhaus"
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
}

data "archive_file" "feodo_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/feodo/handler.py"
  output_path = "${path.module}/../ingestion/build/feodo.zip"
}

resource "aws_lambda_function" "feodo" {
  function_name    = "${var.project_name}-feodo"
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
}

data "archive_file" "cisa_kev_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/cisa_kev/handler.py"
  output_path = "${path.module}/../ingestion/build/cisa_kev.zip"
}

resource "aws_lambda_function" "cisa_kev" {
  function_name    = "${var.project_name}-cisa-kev"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 30
  filename         = data.archive_file.cisa_kev_zip.output_path
  source_code_hash = data.archive_file.cisa_kev_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = local.ingestion_env_common
  }
}

data "archive_file" "abuseipdb_enrich_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/abuseipdb_enrich/handler.py"
  output_path = "${path.module}/../ingestion/build/abuseipdb_enrich.zip"
}

resource "aws_lambda_function" "abuseipdb_enrich" {
  function_name    = "${var.project_name}-abuseipdb-enrich"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 30
  filename         = data.archive_file.abuseipdb_enrich_zip.output_path
  source_code_hash = data.archive_file.abuseipdb_enrich_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      IOC_TABLE         = aws_dynamodb_table.iocs.name
      ABUSEIPDB_API_KEY = var.abuseipdb_api_key
    }
  }
}

data "archive_file" "normalizer_zip" {
  type        = "zip"
  source_file = "${path.module}/../ingestion/normalizer/handler.py"
  output_path = "${path.module}/../ingestion/build/normalizer.zip"
}

resource "aws_lambda_function" "normalizer" {
  function_name    = "${var.project_name}-normalizer"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 60
  filename         = data.archive_file.normalizer_zip.output_path
  source_code_hash = data.archive_file.normalizer_zip.output_base64sha256
  layers           = [aws_lambda_layer_version.deps.arn]

  environment {
    variables = {
      IOC_TABLE = aws_dynamodb_table.iocs.name
    }
  }
}

resource "aws_lambda_permission" "allow_s3_invoke_normalizer" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.normalizer.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.landing.arn
}

data "archive_file" "api_zip" {
  type        = "zip"
  source_file = "${path.module}/../backend/api/handler.py"
  output_path = "${path.module}/../backend/build/api.zip"
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-api"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  timeout          = 15
  filename         = data.archive_file.api_zip.output_path
  source_code_hash = data.archive_file.api_zip.output_base64sha256

  environment {
    variables = {
      IOC_TABLE = aws_dynamodb_table.iocs.name
    }
  }
}
