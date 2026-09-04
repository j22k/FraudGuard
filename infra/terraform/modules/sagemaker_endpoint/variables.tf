variable "project_name" {
  type        = string
  description = "Project name identifier"
  default     = "fraudguard"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev/staging/prod)"
  default     = "dev"
}

variable "sagemaker_role_arn" {
  type        = string
  description = "IAM role ARN for SageMaker to assume"
}

variable "model_package_arn" {
  type        = string
  description = "ARN of approved ModelPackage in the Model Registry"
  default     = ""
}

variable "serverless_enabled" {
  type        = bool
  description = "Whether to deploy as Serverless Endpoint (scales to 0, $0 idle)"
  default     = true
}

variable "instance_type" {
  type        = string
  description = "Instance type if provisioned (e.g. ml.m5.large)"
  default     = "ml.m5.large"
}

variable "instance_count" {
  type        = number
  description = "Initial instance count if provisioned"
  default     = 1
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
