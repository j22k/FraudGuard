variable "function_name" {
  type        = string
  description = "Name of the Lambda function"
}

variable "lambda_role_arn" {
  type        = string
  description = "IAM Role ARN for the Lambda execution role"
}

variable "lambda_zip_path" {
  type        = string
  description = "Local filesystem path to the Lambda deployment package zip"
  default     = "../../lambda/lambda_package.zip"
}

variable "dynamodb_table_name" {
  type        = string
  description = "Name of the DynamoDB table to write flagged fraud transactions"
}

variable "fraud_score_threshold" {
  type        = string
  description = "Threshold above which transactions are flagged for Bedrock explanation"
  default     = "0.9"
}

variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, prod)"
  default     = "dev"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}

variable "handler" {
  type        = string
  description = "Lambda handler entrypoint"
  default     = "handler.handler"
}

variable "extra_env_vars" {
  type        = map(string)
  description = "Additional environment variables"
  default     = {}
}

variable "enable_function_url" {
  type        = bool
  description = "Whether to create a public HTTPS Function URL with CORS"
  default     = false
}

