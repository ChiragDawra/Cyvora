variable "aws_region" {
  description = "AWS region to deploy Cyvora into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Used as a prefix/tag on every resource"
  type        = string
  default     = "cyvora"
}

variable "budget_limit_usd" {
  description = "Monthly AWS spend limit before the Budgets alarm fires"
  type        = number
  default     = 5
}

variable "budget_alert_email" {
  description = "Email address notified when the Budgets alarm threshold is crossed"
  type        = string
  # No default on purpose - must be supplied via terraform.tfvars (gitignored) or -var.
}
