# Banking Fraud Detection and Customer Notification System

A cloud-native banking fraud detection and customer notification system built with **FastAPI, Docker, AWS ECS Fargate, Application Load Balancer, SQS, Lambda, DynamoDB, SNS, IAM, and Terraform**.

The system accepts banking transaction requests, evaluates them using fraud detection rules, approves valid transactions, and sends suspicious transactions to an asynchronous alert-processing pipeline.

## Architecture

```text
Client
  │
  ▼
Application Load Balancer (ALB)
  │
  ▼
ECS Fargate (FastAPI API)
  │
  ▼
Fraud Detection Rules
  │
  ├── Approved ──► HTTP response to client
  │
  └── Flagged ──► SQS ──► Lambda ──► DynamoDB
                          │
                          └──► SNS / log alert
```

The API runs on ECS Fargate behind an Application Load Balancer. It evaluates each transaction using fraud detection rules. Approved transactions return directly to the client, while flagged transactions are sent to SQS. Lambda processes the flagged events, stores fraud records in DynamoDB, and sends or logs customer alerts using SNS.

```mermaid
flowchart LR
    Client[Client] --> ALB[Application Load Balancer]
    ALB --> ECS[ECS Fargate FastAPI API]
    ECS --> Rules[Fraud Detection Rules]
    Rules -->|Approved| Response[API Response]
    Rules -->|Flagged| SQS[SQS Queue]
    SQS --> Lambda[AWS Lambda Processor]
    Lambda --> DynamoDB[DynamoDB Fraud Logs]
    Lambda --> SNS[SNS / Log Alert]
```

The deployed AWS architecture includes:

* **ECS Fargate** for the FastAPI transaction API.
* **Application Load Balancer** to expose the API.
* **SQS** to decouple transaction processing from alerting.
* **Lambda** to process flagged transaction events.
* **DynamoDB** to store fraud logs.
* **SNS** or logs for customer alerts.
* **IAM roles and policies** for secure AWS service access.
* **Terraform** for infrastructure provisioning.

## Fraud Detection Logic

The API evaluates each transaction using deterministic fraud rules.

| Rule                                    | Condition                                                                                           | Result           |
| --------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------- |
| Large withdrawal                        | `transaction_type` is `withdrawal` and `amount >= threshold`                                        | Flag transaction |
| Failed login attempts                   | `failed_login_attempts >= threshold`                                                                | Flag transaction |
| Different location in short time window | Same account has a previous transaction from a different location within the configured time window | Flag transaction |

Default risk score weights:

| Rule                                        | Risk Score |
| ------------------------------------------- | ---------- |
| Large withdrawal                            | `+50`      |
| Failed login attempts                       | `+30`      |
| Different location within short time window | `+40`      |

If the final risk score is greater than `0`, the transaction is marked as `flagged`.

If no fraud rules are triggered, the transaction is marked as `approved`.

The optional `bank_id` field supports multi-tenant fraud thresholds. If `bank_id` is missing or unknown, the system uses the default thresholds.

## API Usage

### Health Check

```http
GET /health
```

Example request:

```bash
curl http://localhost:8000/health
```

Example response:

```json
{
  "status": "healthy",
  "service": "Banking Fraud Detection API"
}
```

### Process Transaction

```http
POST /transactions
```

Request body:

```json
{
  "account_id": "ACC123",
  "bank_id": "default",
  "amount": 120,
  "transaction_type": "deposit",
  "location": "Toronto",
  "timestamp": "2026-06-01T10:00:00",
  "failed_login_attempts": 0
}
```

Fields:

| Field                   | Description                                                    |
| ----------------------- | -------------------------------------------------------------- |
| `account_id`            | Customer account identifier                                    |
| `bank_id`               | Optional tenant/bank identifier for tenant-specific thresholds |
| `amount`                | Transaction amount                                             |
| `transaction_type`      | `withdrawal`, `deposit`, or `transfer`                         |
| `location`              | Transaction location                                           |
| `timestamp`             | Transaction timestamp                                          |
| `failed_login_attempts` | Number of failed login attempts before transaction             |

### Approved Transaction Example

```bash
curl -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC123",
    "amount": 120,
    "transaction_type": "deposit",
    "location": "Toronto",
    "timestamp": "2026-06-01T10:00:00",
    "failed_login_attempts": 0
  }'
```

Example response:

```json
{
  "transaction_id": "a317c756-1772-4c61-aa59-f6e175083cb0",
  "account_id": "ACC123",
  "bank_id": "default",
  "status": "approved",
  "reasons": [],
  "risk_score": 0,
  "message": "Transaction approved",
  "notification_status": null
}
```

### Flagged Transaction Example

```bash
curl -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC999",
    "amount": 9000,
    "transaction_type": "withdrawal",
    "location": "Vancouver",
    "timestamp": "2026-06-01T11:00:00",
    "failed_login_attempts": 5
  }'
```

Example response:

```json
{
  "transaction_id": "575668f0-bf9b-4b2f-a332-410ddddba638",
  "account_id": "ACC999",
  "bank_id": "default",
  "status": "flagged",
  "reasons": [
    "Unusually large withdrawal amount",
    "Too many failed login attempts before transaction"
  ],
  "risk_score": 80,
  "message": "Transaction flagged for review",
  "notification_status": {
    "published": true,
    "destination": "sqs"
  }
}
```

## Deployment Steps

### 1. Configure AWS CLI

```bash
aws configure
aws sts get-caller-identity
```

### 2. Initialize Terraform

```bash
cd infra
terraform init
terraform fmt
terraform validate
```

### 3. Create ECR Repository

```bash
terraform apply \
  -target=aws_ecr_repository.api \
  -var="api_image_uri=placeholder"
```

### 4. Build and Push Docker Image

```bash
ECR_REPOSITORY_URL=$(terraform output -raw ecr_repository_url)
ECR_REGISTRY=${ECR_REPOSITORY_URL%/*}
AWS_REGION=${AWS_REGION:-us-east-1}
IMAGE_TAG=$(date +%Y%m%d%H%M%S)

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker build -t banking-fraud-alert-system ..
docker tag banking-fraud-alert-system:latest "$ECR_REPOSITORY_URL:$IMAGE_TAG"
docker push "$ECR_REPOSITORY_URL:$IMAGE_TAG"
```

### 5. Deploy AWS Infrastructure

```bash
terraform plan \
  -var="api_image_uri=$ECR_REPOSITORY_URL:$IMAGE_TAG"

terraform apply \
  -var="api_image_uri=$ECR_REPOSITORY_URL:$IMAGE_TAG"
```

To configure SNS email alerts:

```bash
terraform apply \
  -var="api_image_uri=$ECR_REPOSITORY_URL:$IMAGE_TAG" \
  -var="alert_email=you@example.com"
```

After deployment, confirm the SNS subscription email from AWS.

### 6. Get Deployed API URL

```bash
terraform output -raw api_url
```

### 7. Validate Deployment

```bash
API_URL=$(terraform output -raw api_url)
DYNAMODB_TABLE_NAME=$(terraform output -raw dynamodb_table_name)
LAMBDA_FUNCTION_NAME=$(terraform output -raw lambda_function_name)
AWS_REGION=${AWS_REGION:-us-east-1}
```

Health check:

```bash
curl "$API_URL/health"
```

Send an approved transaction:

```bash
curl -X POST "$API_URL/transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC123",
    "amount": 120,
    "transaction_type": "deposit",
    "location": "Toronto",
    "timestamp": "2026-06-01T10:00:00",
    "failed_login_attempts": 0
  }'
```

Send a flagged transaction:

```bash
curl -X POST "$API_URL/transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC999",
    "amount": 9000,
    "transaction_type": "withdrawal",
    "location": "Vancouver",
    "timestamp": "2026-06-01T11:00:00",
    "failed_login_attempts": 5
  }'
```

Confirm Lambda processing:

```bash
aws logs tail "/aws/lambda/$LAMBDA_FUNCTION_NAME" \
  --since 10m \
  --region "$AWS_REGION"
```

Confirm DynamoDB fraud log storage:

```bash
aws dynamodb scan \
  --table-name "$DYNAMODB_TABLE_NAME" \
  --region "$AWS_REGION"
```

Deployment validation evidence is available in:

```text
docs/deployment-validation-evidence.md
```

## Bonus Features

**JWT authentication** — Optional; set `ENABLE_AUTH=true` (and a strong `JWT_SECRET_KEY` in production).

Request a token:

```http
POST /auth/token
```

```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"account_id": "ACC123"}'
```

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

When auth is enabled, send `Authorization: Bearer <token>` on `POST /transactions`.

**Kinesis Firehose + S3 analytics** — Lambda streams flagged transactions to Firehose for delivery to an S3 analytics bucket.

**CloudWatch alarms** — Monitors SQS backlog and Lambda processing errors; alerts publish to the SNS fraud-alerts topic.

**Multi-tenant thresholds** — Optional `bank_id` on transactions loads per-bank rules from `config/bank_thresholds.json`.

## Cleanup

```bash
cd infra
terraform destroy -var="api_image_uri=placeholder"
```