terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "AWS FinOps Waste Sentinel"
      ManagedBy   = "Terraform"
      Environment = "Production"
    }
  }
}

# ---------------------------------------------------------------------------
# Zip Packaging for Python Lambda Code
# ---------------------------------------------------------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/lambda_function.py"
  output_path = "${path.module}/lambda_function.zip"
}

# ---------------------------------------------------------------------------
# IAM Execution Role & Security Policies (Least Privilege)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lambda_exec" {
  name = "aws_finops_sentinel_execution_role_v3"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "sentinel_permissions" {
  name        = "aws_finops_sentinel_policy_v3"
  description = "Least privilege read-only policy for scanning unused EC2/EBS/EIP resources and CloudWatch billing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ResourceScanningReadPermissions"
        Effect = "Allow"
        Action = [
          "ec2:DescribeVolumes",
          "ec2:DescribeAddresses",
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchBillingPermissions"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLoggingPermissions"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "sentinel_policy_attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.sentinel_permissions.arn
}

# ---------------------------------------------------------------------------
# CloudWatch Log Group for Lambda Retention
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/aws-finops-waste-sentinel-v3"
  retention_in_days = 14
}

# ---------------------------------------------------------------------------
# AWS Lambda Function Definition
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "finops_sentinel" {
  function_name    = "aws-finops-waste-sentinel-v3"
  description      = "Scans AWS infrastructure for waste (unattached EBS/EIP, stopped EC2) and posts billing summaries to Telegram."
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      TELEGRAM_BOT_TOKEN = var.telegram_bot_token
      TELEGRAM_CHAT_ID   = var.telegram_chat_id
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.sentinel_policy_attach,
    aws_cloudwatch_log_group.lambda_logs
  ]
}

# ---------------------------------------------------------------------------
# Amazon EventBridge (CloudWatch Events) Scheduled Cron Trigger
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "daily_sentinel_cron" {
  name                = "aws-finops-sentinel-daily-trigger"
  description         = "Triggers AWS FinOps Sentinel Lambda daily at 09:00 AM UTC"
  schedule_expression = "cron(0 9 * * ? *)"
}

resource "aws_cloudwatch_event_target" "sentinel_event_target" {
  rule      = aws_cloudwatch_event_rule.daily_sentinel_cron.name
  target_id = "AWSFinOpsSentinelLambdaTarget"
  arn       = aws_lambda_function.finops_sentinel.arn
}

resource "aws_lambda_permission" "allow_eventbridge_invocation" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.finops_sentinel.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_sentinel_cron.arn
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
output "lambda_function_arn" {
  description = "ARN of the deployed FinOps Sentinel Lambda function"
  value       = aws_lambda_function.finops_sentinel.arn
}

output "eventbridge_rule_arn" {
  description = "ARN of the daily EventBridge cron trigger"
  value       = aws_cloudwatch_event_rule.daily_sentinel_cron.arn
}
