# Banking Fraud Alert System

A small fraud-detection demo for banking transactions. The FastAPI service
scores incoming transactions, approves low-risk activity immediately, and
publishes flagged transactions to an asynchronous alert pipeline.

## Architecture

The application is split into two practical parts:

- **FastAPI transaction service**: container-ready using Docker through the
  root `Dockerfile` and `docker-compose.yml`. Locally it runs on port `8000`
  and exposes `/transactions` plus `/health`.
- **Async fraud-alert pipeline**: provisioned by the current Terraform in
  `infra/`. It creates SQS, Lambda, DynamoDB, and IAM resources so flagged
  transactions can be processed independently from the API request path.

In production, the FastAPI container is intended to run on **ECS Fargate behind
an Application Load Balancer (ALB)**. The current Terraform intentionally keeps
the implemented infrastructure focused on the core asynchronous fraud pipeline:

```text
FastAPI container -> SQS -> Lambda -> DynamoDB
```

ECS/Fargate and the ALB are documented below as the production deployment
extension, not as generated Terraform in the current module. This keeps the
project practical and explainable for a take-home assignment while still showing
the intended AWS deployment path.

## Run Locally

Create a local environment file:

```bash
cp .env.example .env
```

Start the FastAPI container:

```bash
docker compose up --build
```

The API will be available at:

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/transactions`

When `SQS_QUEUE_URL` is empty and `LOCAL_FALLBACK_ENABLED=true`, flagged
transactions are written to `local_data/flagged_transactions.jsonl` for local
development.

## Terraform Scope

The Terraform under `infra/` provisions the core asynchronous fraud pipeline:

- SQS queue for flagged transactions
- Lambda processor triggered by SQS
- DynamoDB table for processed flagged transactions
- IAM roles and policies for the Lambda
- KMS encryption for DynamoDB
- X-Ray tracing for Lambda

Deploy from the `infra/` directory:

```bash
terraform init
terraform plan
terraform apply
```

After apply, use the `sqs_queue_url` output as `SQS_QUEUE_URL` for the FastAPI
service.

## Production ECS/Fargate Extension

For production, extend the current Terraform with the container serving layer
that runs the FastAPI Docker image:

- **ECS Cluster** to host the FastAPI service.
- **Task Definition** for the API Docker image, CPU/memory, container port
  `8000`, environment variables, and CloudWatch logging.
- **Fargate Service** to run and scale the FastAPI tasks across private
  subnets.
- **ALB** in public subnets to route HTTP traffic to the service target group.
- **Security Groups** allowing internet traffic to the ALB and only ALB-to-task
  traffic on port `8000`.
- **IAM Task Role** granting the FastAPI task permission to call
  `sqs:SendMessage` on the flagged-transactions SQS queue.

That extension would let public API requests flow through:

```text
Client -> ALB -> ECS Fargate FastAPI task -> SQS -> Lambda -> DynamoDB
```

The ECS/Fargate layer is intentionally not generated here to avoid turning the
take-home into a large networking and deployment exercise. The practical
contract is simple: the production container receives API traffic and publishes
flagged transactions to the SQS queue already created by the current Terraform.
