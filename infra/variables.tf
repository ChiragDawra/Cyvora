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

variable "abusech_auth_key" {
  description = "abuse.ch Auth-Key (auth.abuse.ch), used by the urlhaus and feodo Lambdas"
  type        = string
  sensitive   = true
  # No default - supply via TF_VAR_abusech_auth_key, e.g. through infra/run.sh.
}

variable "abuseipdb_api_key" {
  description = "AbuseIPDB API key, used by the abuseipdb_enrich Lambda"
  type        = string
  sensitive   = true
  # No default - supply via TF_VAR_abuseipdb_api_key, e.g. through infra/run.sh.
}

variable "otx_api_key" {
  description = "AlienVault OTX API key, used by the otx Lambda. The account must also be subscribed to at least one pulse - /pulses/subscribed returns only what it follows."
  type        = string
  sensitive   = true
  # No default - supply via TF_VAR_otx_api_key, e.g. through infra/run.sh.
}
