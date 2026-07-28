# Remote state in S3. Two reasons this isn't optional:
#
# 1. CI can't run `terraform apply` against a state file that only exists on one laptop,
#    and "100% of infra provisioned through Terraform + CI/CD" is a v1 Definition of Done
#    item (see EXECUTION_GUIDE.md).
# 2. Local state is gitignored, so losing the laptop means losing track of every live
#    resource.
#
# `use_lockfile = true` uses S3's own conditional writes for state locking (Terraform
# >= 1.10), so there's no DynamoDB lock table to provision or pay for.
#
# The bucket is hardcoded rather than interpolated because Terraform backends can't use
# variables. Create it once with ./bootstrap.sh before the first `terraform init`.
#
# Note: state contains the Lambda environment variables, which include the abuse.ch and
# AbuseIPDB keys. The bootstrap script enables default encryption and blocks all public
# access on the bucket.
terraform {
  backend "s3" {
    bucket       = "cyvora-tfstate-788292454412"
    key          = "cyvora/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
