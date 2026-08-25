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

variable "tags" {
  type        = map(string)
  description = "Common resource tags"
  default = {
    Project   = "FraudGuard"
    ManagedBy = "Terraform"
  }
}
