variable "model_package_group_name" {
  type        = string
  description = "Name of the SageMaker Model Package Group"
  default     = "fraudguard-model-group"
}

variable "description" {
  type        = string
  description = "Description of the Model Package Group"
  default     = "Model package group for FraudGuard XGBoost models"
}

variable "tags" {
  type        = map(string)
  description = "Resource tags"
  default     = {}
}
