# Raw feed pulls land here before the normalizer Lambda processes them (see
# ingestion/normalizer/handler.py). Every ingestion Lambda writes to this bucket.
resource "aws_s3_bucket" "landing" {
  bucket = "${var.project_name}-landing"
}

resource "aws_s3_bucket_public_access_block" "landing" {
  bucket                  = aws_s3_bucket.landing.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Static frontend build output (frontend/), served through CloudFront - see
# infra/README.md for the CloudFront + Lambda/API Gateway resources still to be added
# once the frontend build pipeline and Lambda packaging exist.
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
