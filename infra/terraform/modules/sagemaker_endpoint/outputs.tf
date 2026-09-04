output "endpoint_name" {
  value       = aws_sagemaker_endpoint.this.name
  description = "Name of the SageMaker real-time endpoint"
}

output "endpoint_arn" {
  value       = aws_sagemaker_endpoint.this.arn
  description = "ARN of the SageMaker real-time endpoint"
}
