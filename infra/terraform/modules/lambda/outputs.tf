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
