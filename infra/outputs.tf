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
