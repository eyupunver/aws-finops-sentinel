variable "aws_region" {
  type        = string
  description = "AWS Region to deploy resources and scan for waste"
  default     = "us-east-1"
}

variable "telegram_bot_token" {
  type        = string
  description = "Telegram Bot Token from BotFather for sending notification alerts"
  sensitive   = true
}

variable "telegram_chat_id" {
  type        = string
  description = "Telegram Chat ID or Channel ID where Sentinel reports will be posted"
  sensitive   = true
}
