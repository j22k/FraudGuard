# ==============================================================================
# 1. SageMaker Pipeline & Job Execution Role
# ==============================================================================
data "aws_iam_policy_document" "sagemaker_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sagemaker_execution_role" {
  name               = "${var.project_name}-sagemaker-execution-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume_role.json

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-sagemaker-execution-role-${var.environment}"
      Environment = var.environment
    }
  )
}

data "aws_iam_policy_document" "sagemaker_policy_doc" {
  statement {
    sid    = "IAMPassRole"
    effect = "Allow"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::*:role/${var.project_name}-sagemaker-execution-role-${var.environment}"
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["sagemaker.amazonaws.com"]
    }
  }

  statement {
    sid    = "SageMakerJobActions"
    effect = "Allow"
    actions = [
      "sagemaker:CreateProcessingJob",
      "sagemaker:DescribeProcessingJob",
      "sagemaker:StopProcessingJob",
      "sagemaker:CreateTrainingJob",
      "sagemaker:DescribeTrainingJob",
      "sagemaker:StopTrainingJob",
      "sagemaker:AddTags",
      "sagemaker:ListTags"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:AbortMultipartUpload"
    ]
    resources = [
      var.s3_bucket_arn,
      "${var.s3_bucket_arn}/*"
    ]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DeleteLogDelivery",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:GetLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutLogEvents",
      "logs:UpdateLogDelivery"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ECRAccess"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "SageMakerModelRegistry"
    effect = "Allow"
    actions = [
      "sagemaker:CreateModelPackageGroup",
      "sagemaker:DescribeModelPackageGroup",
      "sagemaker:CreateModelPackage",
      "sagemaker:DescribeModelPackage",
      "sagemaker:ListModelPackages",
      "sagemaker:UpdateModelPackage",
      "sagemaker:AddTags",
      "sagemaker:ListTags"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "sagemaker_policy" {
  name        = "${var.project_name}-sagemaker-policy-${var.environment}"
  description = "Policy for SageMaker Pipeline execution in FraudGuard"
  policy      = data.aws_iam_policy_document.sagemaker_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "sagemaker_attach" {
  role       = aws_iam_role.sagemaker_execution_role.name
  policy_arn = aws_iam_policy.sagemaker_policy.arn
}

# ==============================================================================
# 2. EventBridge to SageMaker Pipeline Trigger Role
# ==============================================================================
data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge_sagemaker_role" {
  name               = "${var.project_name}-eventbridge-sagemaker-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-eventbridge-sagemaker-role-${var.environment}"
      Environment = var.environment
    }
  )
}

data "aws_iam_policy_document" "eventbridge_sagemaker_policy_doc" {
  statement {
    sid    = "StartSageMakerPipelineExecution"
    effect = "Allow"
    actions = [
      "sagemaker:StartPipelineExecution"
    ]
    resources = [
      var.sagemaker_pipeline_arn
    ]
  }
}

resource "aws_iam_policy" "eventbridge_sagemaker_policy" {
  name        = "${var.project_name}-eventbridge-sagemaker-policy-${var.environment}"
  description = "Allows EventBridge to trigger SageMaker Pipeline"
  policy      = data.aws_iam_policy_document.eventbridge_sagemaker_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "eventbridge_sagemaker_attach" {
  role       = aws_iam_role.eventbridge_sagemaker_role.name
  policy_arn = aws_iam_policy.eventbridge_sagemaker_policy.arn
}

# ==============================================================================
# 3. Lambda Execution Role (for Bedrock Haiku Explainability - Phase 4)
# ==============================================================================
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution_role" {
  name               = "${var.project_name}-lambda-execution-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-lambda-execution-role-${var.environment}"
      Environment = var.environment
    }
  )
}

data "aws_iam_policy_document" "lambda_policy_doc" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid    = "DynamoDBWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem"
    ]
    resources = var.dynamodb_table_arn != "" ? [var.dynamodb_table_arn] : ["*"]
  }

  statement {
    sid    = "BedrockClaudeHaikuInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel"
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-*"
    ]
  }

  statement {
    sid    = "S3ReadInferenceOutput"
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "${var.s3_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_name}-lambda-policy-${var.environment}"
  description = "Policy for Lambda Bedrock explainability & DynamoDB writes"
  policy      = data.aws_iam_policy_document.lambda_policy_doc.json
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}
