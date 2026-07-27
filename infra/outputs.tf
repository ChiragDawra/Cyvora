output "landing_bucket_name" {
  value = aws_s3_bucket.landing.bucket
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "iocs_table_name" {
  value = aws_dynamodb_table.iocs.name
}

output "api_url" {
  description = "API Gateway base URL - pass as NEXT_PUBLIC_API_URL when building the frontend"
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "cloudfront_domain" {
  description = "Public URL for the frontend"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "Needed for `aws cloudfront create-invalidation` after each frontend deploy"
  value       = aws_cloudfront_distribution.frontend.id
}
