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
# 5. EventBridge S3 Trigger Module
# ==============================================================================
module "eventbridge" {
  source                 = "./modules/eventbridge"
  project_name           = var.project_name
  environment            = var.environment
  s3_bucket_name         = module.s3.bucket_id
  sagemaker_pipeline_arn = local.pipeline_arn
  eventbridge_role_arn   = module.iam.eventbridge_sagemaker_role_arn
  tags                   = var.tags
}
