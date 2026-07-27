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

  statement {
    sid = "IocTableReadWrite"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.iocs.arn,
      "${aws_dynamodb_table.iocs.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda_data_access" {
  name   = "${var.project_name}-lambda-data-access"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_data_access.json
}
