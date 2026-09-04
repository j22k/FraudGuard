resource "aws_lambda_function" "this" {
  function_name = var.function_name
  runtime       = "python3.12"
  handler       = var.handler
  role          = var.lambda_role_arn
  filename      = var.lambda_zip_path
  timeout       = 300
  memory_size   = 256

  source_code_hash = fileexists(var.lambda_zip_path) ? filebase64sha256(var.lambda_zip_path) : null

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE        = var.dynamodb_table_name
        FRAUD_SCORE_THRESHOLD = var.fraud_score_threshold
      },
      var.extra_env_vars
    )
  }
}

resource "aws_lambda_function_url" "this" {
  count              = var.enable_function_url ? 1 : 0
  function_name      = aws_lambda_function.this.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["*"]
    allow_headers     = ["*"]
    expose_headers    = ["*"]
    max_age           = 300
  }
}

resource "aws_lambda_permission" "function_url" {
  count                  = var.enable_function_url ? 1 : 0
  statement_id           = "AllowFunctionURLPublic"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.this.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
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
