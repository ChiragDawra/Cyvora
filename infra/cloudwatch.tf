# One error-rate alarm per Lambda, all notifying the same email used for the Budgets
# alarm. Dashboards/latency alarms are left for later - error alarms are the
# highest-value guardrail for a scheduled pipeline nobody's watching in real time.
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.budget_alert_email
}

locals {
  alarm_functions = {
    urlhaus          = aws_lambda_function.urlhaus.function_name
    feodo            = aws_lambda_function.feodo.function_name
    cisa_kev         = aws_lambda_function.cisa_kev.function_name
    abuseipdb_enrich = aws_lambda_function.abuseipdb_enrich.function_name
    normalizer       = aws_lambda_function.normalizer.function_name
    api              = aws_lambda_function.api.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.alarm_functions

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
