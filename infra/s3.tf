# S3 bucket names are globally unique across all AWS accounts, so a bare "cyvora-landing"
# would almost certainly collide on first apply. Suffixing with the account ID keeps the
# names deterministic (no random_id in state) while making collisions impossible.
data "aws_caller_identity" "current" {}

locals {
  bucket_suffix = data.aws_caller_identity.current.account_id
}

# Raw feed pulls land here before the normalizer Lambda processes them (see
# ingestion/normalizer/handler.py). Every ingestion Lambda writes to this bucket.
resource "aws_s3_bucket" "landing" {
  bucket = "${var.project_name}-landing-${local.bucket_suffix}"
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Raw pulls are a staging area, not an archive - the normalizer consumes each object
# within seconds of it landing. Without this rule the bucket grows forever, and S3's 5 GB
# free allowance is a 12-month offer, not an always-free one.
resource "aws_s3_bucket_lifecycle_configuration" "landing" {
  bucket = aws_s3_bucket.landing.id

  rule {
    id     = "expire-raw-pulls"
    status = "Enabled"

    filter {}

    expiration {
      days = 7
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Static frontend build output (frontend/out/), served through CloudFront with Origin
# Access Control - see infra/cloudfront.tf. The bucket itself stays fully private.
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${local.bucket_suffix}"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
