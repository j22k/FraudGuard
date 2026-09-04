output "function_arn" {
  value       = aws_lambda_function.this.arn
  description = "ARN of the Lambda function"
}

output "function_name" {
  value       = aws_lambda_function.this.function_name
  description = "Name of the Lambda function"
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.this.name
  description = "Name of the CloudWatch log group for the Lambda function"
}

output "function_url" {
  value       = var.enable_function_url ? aws_lambda_function_url.this[0].function_url : ""
  description = "Public HTTPS Function URL"
}

