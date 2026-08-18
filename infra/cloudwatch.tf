# One error alarm per Lambda, all notifying the same email used for the Budgets alarm,
# plus one always-free dashboard. Error alarms are the highest-value guardrail for a
# scheduled pipeline nobody's watching in real time.
#
# Six alarms sits inside CloudWatch's always-free 10; one dashboard sits inside its
# always-free 3.
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.budget_alert_email
}

# Plain strings, not aws_lambda_function.*.function_name: the log groups below have to be
# created BEFORE their functions (see the depends_on in infra/lambda.tf), so referencing
# the function resources here would be a dependency cycle.
locals {
  lambda_function_names = {
    urlhaus          = "${var.project_name}-urlhaus"
    feodo            = "${var.project_name}-feodo"
    cisa_kev         = "${var.project_name}-cisa-kev"
    abuseipdb_enrich = "${var.project_name}-abuseipdb-enrich"
    normalizer       = "${var.project_name}-normalizer"
    api              = "${var.project_name}-api"
    anomaly_detector = "${var.project_name}-anomaly-detector"
  }
}

# Lambda auto-creates these on first invocation with retention set to Never Expire, which
# means log storage grows forever and the groups aren't Terraform-managed (so they'd also
# survive `terraform destroy`). Declaring them up front fixes both: 7-day retention keeps
# ingestion well inside CloudWatch's free 5 GB, and the pipeline's logs are only ever
# useful for recent-failure debugging anyway.
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambda_function_names

  name              = "/aws/lambda/${each.value}"
  retention_in_days = 7
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.lambda_function_names

  alarm_name          = "${var.project_name}-${each.key}-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# DynamoDB runs on provisioned capacity inside the always-free 25 WCU/25 RCU (see
# infra/dynamodb.tf), so sustained throttling is the signal that the pipeline is
# outgrowing the free tier - and the thing to catch before it turns into a bill.
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${var.project_name}-dynamodb-throttled-writes"
  namespace           = "AWS/DynamoDB"
  metric_name         = "ThrottledRequests"
  dimensions          = { TableName = aws_dynamodb_table.iocs.name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 3
  threshold           = 500
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  alarm_description = <<-EOT
    Short bursts of throttling are expected and harmless - batch_writer retries them.
    This only fires on sustained throttling (3 straight hours over 500), which means
    the provisioned capacity in infra/dynamodb.tf genuinely needs revisiting.
  EOT
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project_name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Lambda invocations"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 3600
          metrics = [
            for name in values(local.lambda_function_names) :
            ["AWS/Lambda", "Invocations", "FunctionName", name]
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "Lambda errors"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 3600
          metrics = [
            for name in values(local.lambda_function_names) :
            ["AWS/Lambda", "Errors", "FunctionName", name]
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB consumed capacity (free tier: 25 WCU / 25 RCU)"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 3600
          metrics = [
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.iocs.name],
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.iocs.name],
          ]
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway requests and 5xx"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Sum"
          period = 3600
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.api.id],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.api.id],
          ]
        }
      },
    ]
  })
}
