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

output "fraud_analytics_bucket_name" {
  description = "Name of the S3 bucket receiving Firehose fraud analytics records."
  value       = aws_s3_bucket.fraud_analytics.bucket
}

output "firehose_delivery_stream_name" {
  description = "Name of the Kinesis Firehose delivery stream for flagged transactions."
  value       = aws_kinesis_firehose_delivery_stream.fraud_analytics.name
}

output "sqs_backlog_alarm_name" {
  description = "Name of the CloudWatch alarm for SQS fraud backlog spikes."
  value       = aws_cloudwatch_metric_alarm.sqs_fraud_backlog.alarm_name
}

output "lambda_error_alarm_name" {
  description = "Name of the CloudWatch alarm for Lambda processor errors."
  value       = aws_cloudwatch_metric_alarm.lambda_errors.alarm_name
}
