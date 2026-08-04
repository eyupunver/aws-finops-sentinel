# 🛡️ AWS FinOps & Resource Waste Sentinel

![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20EventBridge%20%7C%20CloudWatch-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-Infrastructure%20as%20Code-844FBA?style=for-the-badge&logo=terraform&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12%20(Zero--Dependency)-3776AB?style=for-the-badge&logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD%20Pipeline-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot%20Notifications-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)

An enterprise-grade, zero-dependency serverless FinOps sentinel designed for AWS Free Tier and production accounts. It automatically scans your AWS infrastructure daily for idle and wasteful resources (unattached EBS volumes, unused Elastic IPs, stopped EC2 instances, and estimated billing metric) and dispatches clean, formatted alerts directly to Telegram.

---

## 📐 Architectural Overview

```mermaid
flowchart TD
    subgraph Scheduling ["⏰ Automation Layer"]
        EB["Amazon EventBridge Cron Trigger<br/><i>cron(0 9 * * ? *)</i>"]
    Compute ["⚡ Compute Layer"]
        Lambda["AWS Lambda Function<br/><b>python3.12</b><br/><i>Zero-Dependency (urllib)</i>"]
    end

    subgraph AWS_APIs ["☁️ AWS Infrastructure Scanners"]
        EC2_EBS["EC2 API<br/>• Unattached EBS Volumes<br/>• Unattached Elastic IPs<br/>• Stopped Instances"]
        CW_Billing["CloudWatch API (us-east-1)<br/>• EstimatedCharges Metric"]
    end

    subgraph Notification ["📱 Alerting Layer"]
        Telegram["Telegram Bot API<br/><i>sendMessage (HTML)</i>"]
        User["👨‍💻 DevOps / FinOps Team"]
    end

    EB -->|Invoke Daily 09:00 UTC| Lambda
    Lambda -->|boto3 scan| EC2_EBS
    Lambda -->|boto3 billing query| CW_Billing
    Lambda -->|HTTPS POST via urllib| Telegram
    Telegram -->|Deliver Alert| User
```

---

## ✨ Key Features

- 💾 **Unattached EBS Volume Detection**: Identifies EBS volumes with state `available` and reports Volume ID, Size (GB), and Volume Type.
- 🌐 **Unattached Elastic IP Sentinel**: Pinpoints Elastic IPs lacking an `AssociationId` that accumulate hourly idle charges.
- 🛑 **Stopped EC2 Instance Audit**: Lists all stopped EC2 instances along with Instance ID, Name tag, and Instance Type.
- 💰 **CloudWatch Billing Monitoring**: Queries `us-east-1` CloudWatch `AWS/Billing` metrics for real-time estimated monthly expenditure.
- ⚡ **Zero-Dependency Python Runtime**: Uses standard library `urllib.request` and `json`. Requires **no external Lambda layers** or `pip install` packages.
- 🔒 **Least-Privilege Security**: Minimal IAM policy attached to the Lambda execution role.
- 🤖 **Automated CI/CD**: GitHub Actions workflow powered by Terraform for automated deployment.

---

## 📁 Directory Structure

```text
.
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions CI/CD Pipeline
├── lambda/
│   └── lambda_function.py      # Core Python Lambda code (urllib based)
├── main.tf                     # Infrastructure definition (Lambda, IAM, EventBridge)
├── variables.tf                # Input variable definitions
└── README.md                   # Architecture & Usage Documentation
```

---

## 🔑 Environment Variables & GitHub Secrets

| Variable / Secret Name | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `AWS_REGION` | String | No | Target AWS region (Default: `us-east-1`). |
| `AWS_ACCESS_KEY_ID` | Secret | Yes (CI/CD) | AWS Access Key ID for deployment. |
| `AWS_SECRET_ACCESS_KEY` | Secret | Yes (CI/CD) | AWS Secret Access Key for deployment. |
| `TELEGRAM_BOT_TOKEN` | Secret | Yes | Bot token generated via [@BotFather](https://t.me/BotFather). |
| `TELEGRAM_CHAT_ID` | Secret | Yes | Target Telegram Chat or Channel ID. |

---

## 🚀 Quick Start & Local Execution

### 1. Run Python Script Locally

You can run the script on your workstation without deploying to AWS:

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAFx..."
export TELEGRAM_CHAT_ID="-100123456789"
export AWS_REGION="us-east-1"

python lambda/lambda_function.py
```

---

## 🛠️ Infrastructure Deployment via Terraform

### 1. Prerequisites
- [Terraform CLI >= 1.0.0](https://developer.hashicorp.com/terraform/downloads)
- AWS CLI configured with administrator or deployment credentials.

### 2. Deployment Steps

```bash
# 1. Initialize Terraform
terraform init

# 2. Plan Infrastructure
terraform plan \
  -var="telegram_bot_token=YOUR_BOT_TOKEN" \
  -var="telegram_chat_id=YOUR_CHAT_ID" \
  -var="aws_region=us-east-1"

# 3. Apply Configuration
terraform apply -auto-approve \
  -var="telegram_bot_token=YOUR_BOT_TOKEN" \
  -var="telegram_chat_id=YOUR_CHAT_ID" \
  -var="aws_region=us-east-1"
```

---

## 🔄 CI/CD Pipeline (GitHub Actions)

This repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that automatically runs `terraform apply` whenever code is pushed to the `main` branch.

### Setting Up GitHub Repository Secrets:

Navigate to **Settings > Secrets and variables > Actions** in your GitHub repository and add the following repository secrets:

1. `AWS_ACCESS_KEY_ID`: Your AWS IAM access key.
2. `AWS_SECRET_ACCESS_KEY`: Your AWS IAM secret key.
3. `AWS_REGION`: Target region (e.g. `us-east-1`).
4. `TELEGRAM_BOT_TOKEN`: Telegram bot token.
5. `TELEGRAM_CHAT_ID`: Telegram destination chat ID.

Once configured, any push to `main` will automatically package, plan, and deploy the infrastructure.

---

## 📄 License
This project is open-source under the MIT License.
