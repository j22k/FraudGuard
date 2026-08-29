variable "project_name" {
  type        = string
  description = "Project name prefix"
  default     = "fraudguard"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "s3_bucket_name" {
  type        = string
  description = "S3 bucket name to monitor for new raw transaction uploads"
}

variable "sagemaker_pipeline_arn" {
  type        = string
  description = "ARN of the SageMaker Pipeline to trigger"
}

variable "eventbridge_role_arn" {
  type        = string
  description = "IAM Role ARN for EventBridge to invoke SageMaker Pipeline"
}

variable "lambda_function_arn" {
  type        = string
  description = "ARN of the Lambda function to trigger on batch transform inference output"
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
