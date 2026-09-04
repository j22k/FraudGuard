locals {
  endpoint_name = "${var.project_name}-realtime-endpoint-${var.environment}"
  model_name    = "${var.project_name}-model-${var.environment}"
  config_name   = "${var.project_name}-endpoint-config-${var.environment}"
}

# 1. SageMaker Model Definition
resource "aws_sagemaker_model" "this" {
  name               = local.model_name
  execution_role_arn = var.sagemaker_role_arn

  dynamic "container" {
    for_each = var.model_package_arn != "" ? [1] : []
    content {
      model_package_name = var.model_package_arn
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = local.model_name
      Environment = var.environment
    }
  )
}

# 2. Endpoint Configuration (Serverless or Provisioned)
resource "aws_sagemaker_endpoint_configuration" "this" {
  name = local.config_name

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.this.name
    initial_instance_count = var.serverless_enabled ? null : var.instance_count
    instance_type          = var.serverless_enabled ? null : var.instance_type

    dynamic "serverless_config" {
      for_each = var.serverless_enabled ? [1] : []
      content {
        max_concurrency   = 10
        memory_size_in_mb = 2048
      }
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = local.config_name
      Environment = var.environment
    }
  )
}

# 3. SageMaker Real-Time / Serverless Endpoint
resource "aws_sagemaker_endpoint" "this" {
  name                 = local.endpoint_name
  endpoint_config_name = aws_sagemaker_endpoint_configuration.this.name

  tags = merge(
    var.tags,
    {
      Name        = local.endpoint_name
      Environment = var.environment
    }
  )
}
