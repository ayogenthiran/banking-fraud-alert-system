output "ecr_repository_url" {
  description = "Repository URL for the FastAPI container image."
  value       = aws_ecr_repository.api.repository_url
}

output "alb_dns_name" {
  description = "DNS name of the public API Application Load Balancer."
  value       = aws_lb.api.dns_name
}

output "api_url" {
  description = "HTTP URL for the deployed FastAPI service."
  value       = "http://${aws_lb.api.dns_name}"
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster running the FastAPI service."
  value       = aws_ecs_cluster.api.name
}

output "ecs_service_name" {
  description = "Name of the ECS Fargate service running the FastAPI service."
  value       = aws_ecs_service.api.name
}

output "sqs_queue_url" {
  description = "URL of the SQS queue the API publishes flagged transactions to."
  value       = aws_sqs_queue.flagged_transactions.url
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table storing flagged transactions."
  value       = aws_dynamodb_table.flagged_transactions.name
}

output "lambda_function_name" {
  description = "Name of the Lambda function that processes flagged transactions."
  value       = aws_lambda_function.processor.function_name
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for fraud alerts."
  value       = aws_sns_topic.fraud_alerts.arn
}
