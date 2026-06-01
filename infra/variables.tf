variable "aws_region" {
  description = "AWS region to deploy the fraud-alert infrastructure into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used to name all resources."
  type        = string
  default     = "banking-fraud-alert-system"
}

variable "api_image_uri" {
  description = "Container image URI for the FastAPI fraud detection API."
  type        = string
}

variable "alert_email" {
  description = "Optional email address to subscribe to fraud alert SNS notifications."
  type        = string
  default     = ""
}
