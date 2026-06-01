# AWS Deployment Commands

Use these commands to deploy, test, inspect, and clean up the Banking Fraud Alert System on AWS.

## 1. AWS Login

```bash
aws configure
aws sts get-caller-identity
```

## 2. Terraform Init

```bash
cd infra
terraform init
```

## 3. Create ECR Repository First

Create only the ECR repository before the project image exists. The full ECS service is deployed after the real image is pushed.

```bash
terraform apply \
  -target=aws_ecr_repository.api \
  -var="project_name=banking-fraud-alert-system" \
  -var="aws_region=us-east-1" \
  -var="api_image_uri=placeholder"
```

## 4. Get ECR Repo URL

```bash
export ECR_REPO_URL=$(terraform output -raw ecr_repository_url)
export ECR_REGISTRY=${ECR_REPO_URL%/*}
export AWS_REGION=us-east-1
export IMAGE_TAG=$(date +%Y%m%d%H%M%S)
```

## 5. Build and Push Docker Image

```bash
cd ..
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
docker build -t banking-fraud-alert-system .
docker tag banking-fraud-alert-system:latest $ECR_REPO_URL:$IMAGE_TAG
docker push $ECR_REPO_URL:$IMAGE_TAG
```

## 6. Redeploy With Real Image

```bash
cd infra
terraform apply \
  -var="project_name=banking-fraud-alert-system" \
  -var="aws_region=us-east-1" \
  -var="api_image_uri=$ECR_REPO_URL:$IMAGE_TAG"
```

To receive email alerts, add `-var="alert_email=you@example.com"` to this apply command and confirm the SNS subscription email from AWS.

## 7. Test Health Endpoint

```bash
export API_URL=$(terraform output -raw api_url)
curl $API_URL/health
```

## 8. Test Approved Transaction

```bash
curl -X POST $API_URL/transactions \
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

Expected result: `"status":"approved"`.

## 9. Test Flagged Transaction

```bash
curl -X POST $API_URL/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC123",
    "amount": 7000,
    "transaction_type": "withdrawal",
    "location": "Toronto",
    "timestamp": "2026-06-01T10:05:00",
    "failed_login_attempts": 4
  }'
```

Expected result: `"status":"flagged"`.

## 10. Verify DynamoDB

```bash
aws dynamodb scan \
  --table-name $(terraform output -raw dynamodb_table_name) \
  --region us-east-1
```

## 11. Check Lambda Logs

```bash
aws logs tail "/aws/lambda/$(terraform output -raw lambda_function_name)" \
  --region us-east-1 \
  --since 10m
```

## 12. Cleanup

```bash
terraform destroy \
  -var="project_name=banking-fraud-alert-system" \
  -var="aws_region=us-east-1" \
  -var="api_image_uri=$ECR_REPO_URL:$IMAGE_TAG"
```
