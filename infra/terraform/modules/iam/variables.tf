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

variable "s3_bucket_arn" {
  type        = string
  description = "ARN of the FraudGuard S3 bucket"
}

variable "dynamodb_table_arn" {
  type        = string
  description = "ARN of the DynamoDB table"
  default     = ""
}

variable "sagemaker_pipeline_arn" {
  type        = string
  description = "ARN of the SageMaker Pipeline"
  default     = "*"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
