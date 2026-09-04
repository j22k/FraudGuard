terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

locals {
  bucket_name   = lower(var.s3_bucket_name != "" ? var.s3_bucket_name : "${var.project_name}-data-${var.environment}-${random_id.bucket_suffix.hex}")
  pipeline_name = "${var.project_name}-pipeline"
  pipeline_arn  = "arn:aws:sagemaker:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:pipeline/${local.pipeline_name}"
}

# ==============================================================================
# 1. S3 Module
# ==============================================================================
module "s3" {
  source      = "./modules/s3"
  bucket_name = local.bucket_name
  environment = var.environment
  tags        = var.tags
}

# ==============================================================================
# 2. DynamoDB Module
# ==============================================================================
module "dynamodb" {
  source      = "./modules/dynamodb"
  table_name  = "${var.project_name}-flagged-transactions-${var.environment}"
  environment = var.environment
  tags        = var.tags
}

# ==============================================================================
# 3. IAM Module
# ==============================================================================
module "iam" {
  source                 = "./modules/iam"
  project_name           = var.project_name
  environment            = var.environment
  s3_bucket_arn          = module.s3.bucket_arn
  dynamodb_table_arn     = module.dynamodb.table_arn
  sagemaker_pipeline_arn = local.pipeline_arn
  tags                   = var.tags
}

# ==============================================================================
# 4. SageMaker Model Package Group Module
# ==============================================================================
module "sagemaker" {
  source                   = "./modules/sagemaker"
  model_package_group_name = "${var.project_name}-model-group"
  description              = "Model package group for FraudGuard XGBoost models"
  tags                     = var.tags
}

# ==============================================================================
# 5. Lambda Module (Phase 4 - Bedrock Haiku Explainability)
# ==============================================================================
module "lambda" {
  source                = "./modules/lambda"
  function_name         = "${var.project_name}-explainability-${var.environment}"
  lambda_role_arn       = module.iam.lambda_execution_role_arn
  dynamodb_table_name   = module.dynamodb.table_name
  lambda_zip_path       = var.lambda_zip_path != "" ? var.lambda_zip_path : "${path.module}/../../lambda/lambda_package.zip"
  fraud_score_threshold = var.fraud_score_threshold
  aws_region            = var.aws_region
  environment           = var.environment
  tags                  = var.tags
}

# ==============================================================================
# 6. EventBridge S3 Trigger Module
# ==============================================================================
module "eventbridge" {
  source                 = "./modules/eventbridge"
  project_name           = var.project_name
  environment            = var.environment
  s3_bucket_name         = module.s3.bucket_id
  sagemaker_pipeline_arn = local.pipeline_arn
  eventbridge_role_arn   = module.iam.eventbridge_sagemaker_role_arn
  lambda_function_arn    = module.lambda.function_arn
  tags                   = var.tags
}

# ==============================================================================
# 7. Lambda Permission for EventBridge Trigger (lives in root to prevent circular dep)
# ==============================================================================
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = module.eventbridge.inference_trigger_rule_arn
}

# ==============================================================================
# 8. SageMaker Real-Time / Serverless Endpoint Module
# ==============================================================================
module "sagemaker_endpoint" {
  count              = var.enable_realtime_endpoint ? 1 : 0
  source             = "./modules/sagemaker_endpoint"
  project_name       = var.project_name
  environment        = var.environment
  sagemaker_role_arn = module.iam.sagemaker_execution_role_arn
  model_package_arn  = var.approved_model_package_arn
  serverless_enabled = var.realtime_serverless_enabled
  tags               = var.tags
}

# ==============================================================================
# 9. Real-Time Orchestrator Lambda Module (with public HTTPS Function URL)
# ==============================================================================
module "realtime_lambda" {
  count                 = var.enable_realtime_endpoint ? 1 : 0
  source                = "./modules/lambda"
  function_name         = "${var.project_name}-realtime-api-${var.environment}"
  handler               = "realtime_handler.lambda_handler"
  lambda_role_arn       = module.iam.lambda_execution_role_arn
  dynamodb_table_name   = module.dynamodb.table_name
  lambda_zip_path       = var.lambda_zip_path != "" ? var.lambda_zip_path : "${path.module}/../../lambda/lambda_package.zip"
  fraud_score_threshold = var.fraud_score_threshold
  aws_region            = var.aws_region
  environment           = var.environment
  enable_function_url   = true
  extra_env_vars = {
    SAGEMAKER_ENDPOINT_NAME = module.sagemaker_endpoint[0].endpoint_name
  }
  tags = var.tags
}

# ==============================================================================
# 10. HTTP API Gateway Module
# ==============================================================================
module "api_gateway" {
  count                = var.enable_realtime_endpoint ? 1 : 0
  source               = "./modules/api_gateway"
  project_name         = var.project_name
  environment          = var.environment
  lambda_function_arn  = module.realtime_lambda[0].function_arn
  lambda_function_name = module.realtime_lambda[0].function_name
  tags                 = var.tags
}
