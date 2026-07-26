output "landing_bucket_name" {
  value = aws_s3_bucket.landing.bucket
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "iocs_table_name" {
  value = aws_dynamodb_table.iocs.name
}
