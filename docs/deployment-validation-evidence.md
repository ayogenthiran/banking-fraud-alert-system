# Deployment Validation Evidence

This document captures terminal evidence from the AWS deployment validation for the Banking Fraud Alert System.

## Terraform API Output

Command:

```bash
terraform output api_url
```

Output:

```text
"http://banking-fraud-alert-system-alb-1896298204.us-east-1.elb.amazonaws.com"
```

## Health Check

Command:

```bash
curl "$API_URL/health"
```

Output:

```json
{"status":"healthy","service":"Banking Fraud Detection API"}
```

## Approved Transaction

Command:

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

Output:

```json
{"transaction_id":"a317c756-1772-4c61-aa59-f6e175083cb0","account_id":"ACC123","status":"approved","reasons":[],"risk_score":0,"message":"Transaction approved","notification_status":null}
```

## Flagged Transaction Published To SQS

Command:

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

Output:

```json
{"transaction_id":"575668f0-bf9b-4b2f-a332-410ddddba638","account_id":"ACC999","status":"flagged","reasons":["Unusually large withdrawal amount","Too many failed login attempts before transaction"],"risk_score":80,"message":"Transaction flagged for review","notification_status":{"published":true,"destination":"sqs"}}
```

## Lambda CloudWatch Logs

Command:

```bash
aws logs filter-log-events \
  --region "$AWS_REGION" \
  --log-group-name "/aws/lambda/$LAMBDA_FUNCTION_NAME" \
  --start-time $((($(date +%s) - 600) * 1000)) \
  --query 'events[*].message' \
  --output text
```

Output excerpt:

```text
START RequestId: 4fa3a08f-5de5-516b-82d0-c218b0bf1e4f Version: $LATEST
DynamoDB write succeeded: table=banking-fraud-alert-system-flagged-transactions transaction_id=c62cf429-18b8-4de9-9dbd-bfdb5ec4a414
END RequestId: 4fa3a08f-5de5-516b-82d0-c218b0bf1e4f
REPORT RequestId: 4fa3a08f-5de5-516b-82d0-c218b0bf1e4f Duration: 563.95 ms Billed Duration: 564 ms Memory Size: 128 MB Max Memory Used: 89 MB

START RequestId: 1b0a53fb-abc7-5f65-8d83-316c453520fb Version: $LATEST
DynamoDB write succeeded: table=banking-fraud-alert-system-flagged-transactions transaction_id=575668f0-bf9b-4b2f-a332-410ddddba638
END RequestId: 1b0a53fb-abc7-5f65-8d83-316c453520fb
REPORT RequestId: 1b0a53fb-abc7-5f65-8d83-316c453520fb Duration: 7313.46 ms Billed Duration: 7446 ms Memory Size: 128 MB Max Memory Used: 87 MB
```

## DynamoDB Fraud Log

Command:

```bash
aws dynamodb scan --table-name "$DYNAMODB_TABLE_NAME" --region "$AWS_REGION"
```

Output excerpt:

```json
{
  "Items": [
    {
      "location": {
        "S": "Vancouver"
      },
      "failed_login_attempts": {
        "N": "5"
      },
      "timestamp": {
        "S": "2026-06-01T11:00:00"
      },
      "status": {
        "S": "flagged"
      },
      "amount": {
        "N": "9000"
      },
      "transaction_id": {
        "S": "575668f0-bf9b-4b2f-a332-410ddddba638"
      },
      "account_id": {
        "S": "ACC999"
      },
      "transaction_type": {
        "S": "withdrawal"
      },
      "risk_score": {
        "N": "80"
      }
    }
  ],
  "Count": 4,
  "ScannedCount": 4,
  "ConsumedCapacity": null
}
```

## SNS Email Subscription

Command:

```bash
aws sns list-subscriptions-by-topic --topic-arn "$SNS_TOPIC_ARN" --region "$AWS_REGION"
```

Output before email confirmation:

```json
{
  "Subscriptions": [
    {
      "SubscriptionArn": "PendingConfirmation",
      "Owner": "315527911051",
      "Protocol": "email",
      "Endpoint": "ayogenthiran.ai@gmail.com",
      "TopicArn": "arn:aws:sns:us-east-1:315527911051:banking-fraud-alert-system-fraud-alerts"
    }
  ]
}
```

Output after email confirmation:

```json
{
  "Subscriptions": [
    {
      "SubscriptionArn": "arn:aws:sns:us-east-1:315527911051:banking-fraud-alert-system-fraud-alerts:68d7868f-6ddb-4f91-9e06-60ae97b035f6",
      "Owner": "315527911051",
      "Protocol": "email",
      "Endpoint": "ayogenthiran.ai@gmail.com",
      "TopicArn": "arn:aws:sns:us-east-1:315527911051:banking-fraud-alert-system-fraud-alerts"
    }
  ]
}
```

## Post-Confirmation Flagged Transaction

Command:

```bash
curl -X POST "$API_URL/transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "ACC777",
    "amount": 9500,
    "transaction_type": "withdrawal",
    "location": "Montreal",
    "timestamp": "2026-06-01T12:00:00",
    "failed_login_attempts": 5
  }'
```

Output:

```json
{"transaction_id":"51eae07f-3b7c-4c8f-afd7-99faa6e65c6c","account_id":"ACC777","status":"flagged","reasons":["Unusually large withdrawal amount","Too many failed login attempts before transaction"],"risk_score":80,"message":"Transaction flagged for review","notification_status":{"published":true,"destination":"sqs"}}
```
