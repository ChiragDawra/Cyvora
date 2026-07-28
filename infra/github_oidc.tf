# Lets GitHub Actions assume a role in this account using a short-lived OIDC token, so
# CI never holds a long-lived AWS access key. Both the OIDC provider and the role are
# free - IAM has no charge.
#
# The role is what .github/workflows/deploy.yml assumes; its ARN goes into the repo's
# AWS_ROLE_ARN variable (Settings > Secrets and variables > Actions > Variables).

variable "github_repository" {
  description = "owner/repo allowed to assume the deploy role via OIDC"
  type        = string
  default     = "ChiragDawra/Cyvora"
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

variable "create_github_oidc_provider" {
  description = <<-EOT
    Create the GitHub OIDC provider, or reuse an existing one. An AWS account can only
    have one provider per URL, so set this to false if the account already has one from
    another project.
  EOT
  type        = bool
  default     = true
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_github_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  github_oidc_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to pushes on main of this one repo. Without this the role would be
    # assumable from any fork's workflow.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json
}

# Broad on purpose: this role runs `terraform apply` over the whole stack, so it needs to
# create and destroy every service the project uses. It is still far narrower than the
# AdministratorAccess on the local Cyvora-Terraform user, and it can only be assumed from
# main of this repo.
resource "aws_iam_role_policy_attachment" "github_actions" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
    "arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator",
    "arn:aws:iam::aws:policy/CloudFrontFullAccess",
    "arn:aws:iam::aws:policy/CloudWatchFullAccess",
    "arn:aws:iam::aws:policy/AmazonEventBridgeSchedulerFullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/IAMFullAccess",
  ])

  role       = aws_iam_role.github_actions.name
  policy_arn = each.value
}

# No managed policy covers plain Budgets read/write (the AWSBudgets* ones are about
# budget *actions*), so the Budgets alarm needs its own statement.
data "aws_iam_policy_document" "github_actions_budgets" {
  statement {
    actions = [
      "budgets:ViewBudget",
      "budgets:ModifyBudget",
      "budgets:CreateBudget",
      "budgets:DeleteBudget",
      "budgets:DescribeBudget",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions_budgets" {
  name   = "${var.project_name}-github-actions-budgets"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_budgets.json
}

output "github_actions_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable in GitHub Actions"
  value       = aws_iam_role.github_actions.arn
}
