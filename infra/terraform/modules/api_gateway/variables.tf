variable "project_name" {
  type        = string
  description = "Project name identifier"
  default     = "fraudguard"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "lambda_function_arn" {
  type        = string
  description = "ARN of the real-time Lambda function"
}

variable "lambda_function_name" {
  type        = string
  description = "Name of the real-time Lambda function"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
