# Banking Fraud Alert System - core AWS infrastructure.
#
# This Terraform provisions the asynchronous "flagged transaction" pipeline:
#
#     FastAPI transaction service  ->  SQS  ->  Lambda  ->  DynamoDB
#
# Scope note (intentional):
#   The transaction-scoring API is container-ready through Docker (see the root
#   Dockerfile and docker-compose.yml). In production, that container is intended
#   to run on ECS Fargate behind an Application Load Balancer.
#
#   The ECS/Fargate deployment extension would include an ECS cluster, task
#   definition, Fargate service, ALB, target group, security groups, and an IAM
#   task role with sqs:SendMessage permission for this queue. Those resources
#   are deliberately documented instead of generated here to keep the assignment
#   focused on the event-driven fraud-alert path. They can be layered on later
#   without changing the core pipeline below.

terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# SQS queue for flagged transactions
# ---------------------------------------------------------------------------
# The API publishes flagged transactions here; the Lambda consumes them.
resource "aws_sqs_queue" "flagged_transactions" {
  name                       = "${var.project_name}-flagged-transactions"
  visibility_timeout_seconds = 60     # should be >= the Lambda timeout
  message_retention_seconds  = 345600 # 4 days
}

# ---------------------------------------------------------------------------
# DynamoDB table for flagged transactions
# ---------------------------------------------------------------------------
# Customer-managed KMS key used to encrypt the table at rest.
resource "aws_kms_key" "dynamodb" {
  description         = "${var.project_name} DynamoDB encryption key"
  enable_key_rotation = true
}

# On-demand billing keeps this simple and cheap for the demo.
resource "aws_dynamodb_table" "flagged_transactions" {
  name         = "${var.project_name}-flagged-transactions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "transaction_id"

  attribute {
    name = "transaction_id"
    type = "S"
  }

  # Encrypt at rest with the customer-managed KMS key defined above.
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.dynamodb.arn
  }
}

# ---------------------------------------------------------------------------
# IAM role for the Lambda function
# ---------------------------------------------------------------------------
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

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# ---------------------------------------------------------------------------
# IAM policy: SQS read + DynamoDB write + CloudWatch Logs
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_permissions" {
  # Read messages from the SQS queue (required for the event source mapping).
  statement {
    sid    = "ReadFromSQS"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.flagged_transactions.arn]
  }

  # Write flagged transactions to DynamoDB.
  statement {
    sid    = "WriteToDynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [aws_dynamodb_table.flagged_transactions.arn]
  }

  # Write logs to CloudWatch Logs.
  statement {
    sid    = "WriteCloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  # Allow the function to publish X-Ray trace segments (tracing enabled below).
  statement {
    sid    = "WriteXRayTraces"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project_name}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# ---------------------------------------------------------------------------
# Package lambda/handler.py into a deployable zip
# ---------------------------------------------------------------------------
# boto3 is provided by the Lambda runtime, so zipping the handler source is
# sufficient for this demo (no vendored dependencies needed).
data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/handler.py"
  output_path = "${path.module}/build/lambda.zip"
}

# ---------------------------------------------------------------------------
# Lambda function
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "processor" {
  function_name    = "${var.project_name}-processor"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  # Enable X-Ray tracing for end-to-end visibility into invocations.
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      # AWS_REGION is reserved and injected by the Lambda runtime, so it is
      # not set here. The handler reads it automatically.
      DYNAMODB_TABLE_NAME    = aws_dynamodb_table.flagged_transactions.name
      LOCAL_FALLBACK_ENABLED = "false"
    }
  }
}

# ---------------------------------------------------------------------------
# Event source mapping: SQS -> Lambda
# ---------------------------------------------------------------------------
resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = aws_sqs_queue.flagged_transactions.arn
  function_name    = aws_lambda_function.processor.arn
  batch_size       = 10
  enabled          = true
}
