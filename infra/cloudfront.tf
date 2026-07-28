# Serves the statically-exported Next.js app (frontend/out/, see next.config.ts's
# output: "export") from the frontend S3 bucket via CloudFront + Origin Access
# Control - the bucket itself stays fully private (see aws_s3_bucket_public_access_block
# "frontend" in s3.tf).
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "frontend-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # PriceClass_100 (North America + Europe edges only) rather than the default global
  # class. Requests served from those edges are the cheapest, and CloudFront's always-free
  # 1 TB/month applies regardless - this just avoids paying premium-region rates if the
  # site ever gets traffic from Asia/South America.
  price_class = "PriceClass_100"

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "frontend-s3"
    viewer_protocol_policy = "redirect-to-https"

    # AWS-managed CachingOptimized policy, replacing the deprecated forwarded_values
    # block. Same effect (no query strings, no cookies, no headers in the cache key) plus
    # gzip/brotli compression, which cuts origin transfer on the globe.gl bundle.
    cache_policy_id = data.aws_cloudfront_cache_policy.optimized.id
    compress        = true
  }

  # Next.js static export has no server to handle unknown paths - route both to the
  # SPA's own 404 page instead of CloudFront's default error page.
  custom_error_response {
    error_code         = 404
    response_code      = 404
    response_page_path = "/404.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "frontend_cloudfront_read" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_cloudfront_read.json
}

data "aws_iam_policy_document" "frontend_cloudfront_read" {
  statement {
    sid       = "AllowCloudFrontServicePrincipalReadOnly"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}
