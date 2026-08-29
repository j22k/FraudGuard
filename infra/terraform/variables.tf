variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Project name prefix"
  default     = "fraudguard"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, prod)"
  default     = "dev"
}

variable "s3_bucket_name" {
  type        = string
  description = "Custom S3 bucket name. If empty, a unique name will be generated."
  default     = ""
}

variable "fraud_score_threshold" {
  type        = string
  description = "Threshold above which transactions are flagged for Bedrock explanation"
  default     = "0.9"
}

variable "lambda_zip_path" {
  type        = string
  description = "Path to the packaged Lambda zip file. If empty, defaults to ../../lambda/lambda_package.zip relative to this dir."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags"
  default = {
    Project   = "FraudGuard"
    ManagedBy = "Terraform"
  }
}
