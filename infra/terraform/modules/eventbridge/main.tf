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
