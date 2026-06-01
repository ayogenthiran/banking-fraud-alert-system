# Infrastructure

This Terraform module provisions the core AWS resources for the asynchronous
fraud-alert pipeline:

```text
FastAPI transaction service -> SQS -> Lambda -> DynamoDB
```

The FastAPI service itself is container-ready through the root `Dockerfile` and
can be run locally with Docker Compose. For this assignment, the Terraform keeps
the implemented infrastructure focused on the event-driven backend pipeline and
does not create the production container serving layer.

## Resources

- SQS queue for flagged transaction messages.
- Lambda function that consumes the queue.
- DynamoDB table for persisted flagged transactions.
- IAM role and policy for Lambda to read SQS, write DynamoDB, write logs, and
  publish X-Ray traces.
- KMS key for DynamoDB server-side encryption.
- SQS event source mapping for Lambda.

## Usage

From this directory:

```bash
terraform init
terraform plan
terraform apply
```

The module outputs the SQS queue URL, DynamoDB table name, and Lambda function
name. The API container should use the `sqs_queue_url` output as its
`SQS_QUEUE_URL` setting when running against AWS.

## Production ECS/Fargate Extension

In production, the FastAPI Docker container should run on ECS Fargate behind an
Application Load Balancer. That production deployment extension would add:

- **ECS Cluster** for the containerized FastAPI service.
- **Task Definition** pointing to the built API image, exposing container port
  `8000`, setting `SQS_QUEUE_URL`, and sending logs to CloudWatch.
- **Fargate Service** to keep the desired number of API tasks running and
  registered with the load balancer.
- **ALB** with a listener and target group forwarding requests to the Fargate
  service.
- **Security Groups** that allow public HTTP/HTTPS traffic to the ALB and only
  ALB-originated traffic from the ALB security group to the API tasks.
- **IAM Task Role** with `sqs:SendMessage` permission scoped to the
  flagged-transactions SQS queue.

Those resources are documented as the production deployment path rather than
implemented here so the Terraform remains practical for a take-home assignment.
The current module can be applied independently and later reused by the
ECS/Fargate layer through its SQS queue output.
