variable "table_name" {
  type        = string
  description = "Name of the DynamoDB table"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
