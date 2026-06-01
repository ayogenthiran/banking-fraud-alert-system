variable "aws_region" {
  description = "AWS region to deploy the fraud-alert infrastructure into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used to name all resources (queue, table, Lambda, IAM)."
  type        = string
  default     = "banking-fraud-alert"
}
