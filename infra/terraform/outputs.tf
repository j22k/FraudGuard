output "s3_bucket_name" {
  value       = module.s3.bucket_id
  description = "FraudGuard S3 Bucket Name (use as FRAUDGUARD_S3_BUCKET)"
}

output "s3_bucket_arn" {
  value       = module.s3.bucket_arn
  description = "FraudGuard S3 Bucket ARN"
}

output "sagemaker_role_arn" {
  value       = module.iam.sagemaker_execution_role_arn
  description = "SageMaker Execution Role ARN (use as SAGEMAKER_ROLE_ARN)"
}

output "dynamodb_table_name" {
  value       = module.dynamodb.table_name
  description = "DynamoDB Table Name for flagged transactions"
}

output "model_package_group_name" {
  value       = module.sagemaker.model_package_group_name
  description = "SageMaker Model Package Group Name"
}

output "eventbridge_s3_trigger_rule" {
  value       = module.eventbridge.rule_name
  description = "EventBridge Rule name that triggers the SageMaker Pipeline"
}

output "eventbridge_inference_trigger_rule" {
  value       = module.eventbridge.inference_trigger_rule_name
  description = "EventBridge Rule name that triggers the Lambda Explainability function"
}

output "lambda_execution_role_arn" {
  value       = module.iam.lambda_execution_role_arn
  description = "Lambda Execution Role ARN for Bedrock explainability"
}

output "lambda_function_name" {
  value       = module.lambda.function_name
  description = "Name of the Lambda explainability function (use as LAMBDA_FUNCTION_NAME)"
}

output "lambda_function_arn" {
  value       = module.lambda.function_arn
  description = "ARN of the Lambda explainability function"
}
