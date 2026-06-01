# Banking Fraud Alert System - core AWS infrastructure.
#
# This Terraform provisions the fraud detection API and asynchronous
# "flagged transaction" pipeline:
#
#     ALB  ->  ECS Fargate API  ->  SQS  ->  Lambda  ->  DynamoDB + SNS
#
# It uses the default VPC and default public subnets for a compact assignment
# deployment. No custom VPC or NAT Gateway is created.

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

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ---------------------------------------------------------------------------
# ECR repository for the FastAPI container image
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "api" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
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
# SNS topic for fraud alerts
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "fraud_alerts" {
  name = "${var.project_name}-fraud-alerts"
}

resource "aws_sns_topic_subscription" "fraud_alerts_email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.fraud_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------------------------------------------------------------------------
# ECS and ALB networking
# ---------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Allow public HTTP traffic to the API load balancer."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP from the internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Allow ALB traffic to the ECS API tasks."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "API traffic from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "api" {
  name               = "${var.project_name}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id

  health_check {
    enabled = true
    path    = "/health"
  }
}

resource "aws_lb_listener" "api_http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ---------------------------------------------------------------------------
# ECS cluster, roles, task definition, and service
# ---------------------------------------------------------------------------
resource "aws_ecs_cluster" "api" {
  name = "${var.project_name}-cluster"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project_name}/fraud-api"
  retention_in_days = 14
}

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.project_name}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
}

data "aws_iam_policy_document" "ecs_task_permissions" {
  statement {
    sid       = "SendFlaggedTransactions"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.flagged_transactions.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task" {
  name   = "${var.project_name}-ecs-task-policy"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_permissions.json
}

resource "aws_ecs_task_definition" "api" {
  family                   = var.project_name
  cpu                      = "256"
  memory                   = "512"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "fraud-api"
      image     = var.api_image_uri
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "APP_NAME"
          value = "Banking Fraud Detection API"
        },
        {
          name  = "ENVIRONMENT"
          value = "aws"
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "SQS_QUEUE_URL"
          value = aws_sqs_queue.flagged_transactions.url
        },
        {
          name  = "DYNAMODB_TABLE_NAME"
          value = aws_dynamodb_table.flagged_transactions.name
        },
        {
          name  = "LOCAL_FALLBACK_ENABLED"
          value = "false"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.api.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "fraud-api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.api_http]
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
# IAM policy: SQS read + DynamoDB write + SNS publish + CloudWatch Logs
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
    sid       = "WriteToDynamoDB"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.flagged_transactions.arn]
  }

  # Allow DynamoDB writes against the customer-managed table encryption key.
  statement {
    sid    = "UseDynamoDBKmsKey"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.dynamodb.arn]
  }

  # Publish fraud alert notifications.
  statement {
    sid       = "PublishFraudAlerts"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.fraud_alerts.arn]
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
      ENVIRONMENT            = "aws"
      DYNAMODB_TABLE_NAME    = aws_dynamodb_table.flagged_transactions.name
      LOCAL_FALLBACK_ENABLED = "false"
      SNS_TOPIC_ARN          = aws_sns_topic.fraud_alerts.arn
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
