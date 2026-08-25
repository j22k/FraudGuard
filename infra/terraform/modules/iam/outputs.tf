output "sagemaker_execution_role_arn" {
  value       = aws_iam_role.sagemaker_execution_role.arn
  description = "ARN of the SageMaker Execution Role"
}

output "eventbridge_sagemaker_role_arn" {
  value       = aws_iam_role.eventbridge_sagemaker_role.arn
  description = "ARN of the EventBridge Role for triggering SageMaker Pipeline"
}

output "lambda_execution_role_arn" {
  value       = aws_iam_role.lambda_execution_role.arn
  description = "ARN of the Lambda Execution Role"
}
