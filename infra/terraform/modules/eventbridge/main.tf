resource "aws_cloudwatch_event_rule" "s3_raw_upload_rule" {
  name        = "${var.project_name}-s3-raw-trigger-${var.environment}"
  description = "Triggers FraudGuard SageMaker Pipeline when new raw CSV is uploaded"

  event_pattern = jsonencode({
    "source" : ["aws.s3"],
    "detail-type" : ["Object Created"],
    "detail" : {
      "bucket" : {
        "name" : [var.s3_bucket_name]
      },
      "object" : {
        "key" : [{ "prefix" : "raw/" }]
      }
    }
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-s3-raw-trigger-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_cloudwatch_event_target" "sagemaker_pipeline" {
  rule      = aws_cloudwatch_event_rule.s3_raw_upload_rule.name
  target_id = "TriggerSageMakerPipeline"
  arn       = var.sagemaker_pipeline_arn
  role_arn  = var.eventbridge_role_arn

  sagemaker_pipeline_target {
    pipeline_parameter_list {
      name  = "RawDataS3Uri"
      value = "s3://${var.s3_bucket_name}/raw/train_transaction.csv"
    }
  }
}

# ==============================================================================
# Rule 2: S3 inference output -> Lambda Explainability Trigger (Phase 4)
# ==============================================================================
resource "aws_cloudwatch_event_rule" "s3_inference_output_rule" {
  name        = "${var.project_name}-s3-inference-trigger-${var.environment}"
  description = "Triggers FraudGuard Lambda explainability handler when batch transform writes inference output"

  event_pattern = jsonencode({
    "source" : ["aws.s3"],
    "detail-type" : ["Object Created"],
    "detail" : {
      "bucket" : {
        "name" : [var.s3_bucket_name]
      },
      "object" : {
        "key" : [{ "prefix" : "inference-output/" }]
      }
    }
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-s3-inference-trigger-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_cloudwatch_event_target" "lambda_inference_trigger" {
  rule      = aws_cloudwatch_event_rule.s3_inference_output_rule.name
  target_id = "TriggerLambdaExplainability"
  arn       = var.lambda_function_arn
}
