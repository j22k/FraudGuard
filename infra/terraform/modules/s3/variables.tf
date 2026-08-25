variable "bucket_name" {
  type        = string
  description = "Name of the S3 bucket for FraudGuard"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g. dev, prod)"
  default     = "dev"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
