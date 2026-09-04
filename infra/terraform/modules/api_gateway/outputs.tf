output "api_endpoint_url" {
  value       = aws_apigatewayv2_stage.default.invoke_url
  description = "Base invocation URL for HTTP API Gateway"
}

output "api_id" {
  value       = aws_apigatewayv2_api.this.id
  description = "ID of HTTP API Gateway"
}
