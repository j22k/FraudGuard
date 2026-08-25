output "model_package_group_arn" {
  value       = aws_sagemaker_model_package_group.this.arn
  description = "ARN of the SageMaker Model Package Group"
}

output "model_package_group_name" {
  value       = aws_sagemaker_model_package_group.this.model_package_group_name
  description = "Name of the SageMaker Model Package Group"
}
