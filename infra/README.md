# Infrastructure

This Terraform module provisions the core AWS resources for the deployed
fraud-alert system:

```text
ALB -> ECS Fargate FastAPI service -> SQS -> Lambda -> DynamoDB + SNS + Firehose -> S3
```

CloudWatch alarms on SQS backlog and Lambda errors publish to the SNS fraud-alerts topic.

The FastAPI service is built from the root `Dockerfile`, pushed to ECR, and run
on ECS Fargate behind a public Application Load Balancer.

## Resources

- ECR repository for the FastAPI container image.
- ECS cluster, task definition, Fargate service, and CloudWatch log group.
- Public Application Load Balancer, listener, target group, and security groups.
- SQS queue for flagged transaction messages from the API.
- Lambda function that consumes the queue.
- DynamoDB table for persisted flagged transactions.
- SNS topic for customer fraud alerts, with an optional email subscription.
- IAM roles and policies for ECS and Lambda.
- KMS key for DynamoDB server-side encryption.
- S3 bucket and Kinesis Firehose delivery stream for flagged-transaction analytics.
- CloudWatch alarms for SQS backlog and Lambda processing errors.
- SQS event source mapping for Lambda.

## Usage

From this directory:

```bash
terraform init
terraform plan
terraform apply
```

The module outputs the public `api_url`, ECR repository URL, SQS queue URL,
DynamoDB table name, Lambda function name, and SNS topic ARN.

Set `alert_email` during apply to subscribe an email address to the SNS topic.
AWS sends a confirmation email before notifications are delivered.

## Destroy

```bash
BUCKET=$(terraform output -raw fraud_analytics_bucket_name)
aws s3 rm "s3://$BUCKET" --recursive
terraform destroy -var="api_image_uri=placeholder"
```
