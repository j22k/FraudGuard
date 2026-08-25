output "rule_arn" {
  value       = aws_cloudwatch_event_rule.s3_raw_upload_rule.arn
  description = "ARN of the S3 raw upload EventBridge rule"
}

output "rule_name" {
  value       = aws_cloudwatch_event_rule.s3_raw_upload_rule.name
  description = "Name of the S3 raw upload EventBridge rule"
}
