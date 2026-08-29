output "rule_arn" {
  value       = aws_cloudwatch_event_rule.s3_raw_upload_rule.arn
  description = "ARN of the S3 raw upload EventBridge rule"
}

output "rule_name" {
  value       = aws_cloudwatch_event_rule.s3_raw_upload_rule.name
  description = "Name of the S3 raw upload EventBridge rule"
}

output "inference_trigger_rule_arn" {
  value       = aws_cloudwatch_event_rule.s3_inference_output_rule.arn
  description = "ARN of the S3 inference output EventBridge rule"
}

output "inference_trigger_rule_name" {
  value       = aws_cloudwatch_event_rule.s3_inference_output_rule.name
  description = "Name of the S3 inference output EventBridge rule"
}
