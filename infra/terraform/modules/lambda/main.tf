resource "aws_lambda_function" "this" {
  function_name = var.function_name
  runtime       = "python3.12"
  handler       = "handler.handler"
  role          = var.lambda_role_arn
  filename      = var.lambda_zip_path
  timeout       = 300
  memory_size   = 256

  source_code_hash = fileexists(var.lambda_zip_path) ? filebase64sha256(var.lambda_zip_path) : null

  environment {
    variables = {
      DYNAMODB_TABLE        = var.dynamodb_table_name
      FRAUD_SCORE_THRESHOLD = var.fraud_score_threshold
    }
  }
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 14

  tags = merge(
    var.tags,
    {
      Name        = "/aws/lambda/${var.function_name}"
      Environment = var.environment
    }
  )
}
