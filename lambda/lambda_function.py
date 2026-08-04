"""AWS FinOps & Resource Waste Sentinel.

Serverless Python script designed for AWS Lambda and local execution.
Scans AWS resources for waste (unattached EBS volumes, unattached Elastic IPs,
stopped EC2 instances) and fetches CloudWatch estimated billing metrics,
sending a formatted report via Telegram Bot API using Python built-in urllib.

Author: Senior Python & AWS Cloud Architect
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add handler for local execution logging consistency if not present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(console_handler)

# ---------------------------------------------------------------------------
# Environment Variables & Fallbacks
# ---------------------------------------------------------------------------
DEFAULT_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", os.environ.get("BOT_TOKEN", ""))
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("CHAT_ID", ""))


# ---------------------------------------------------------------------------
# AWS Scanning Helper Functions
# ---------------------------------------------------------------------------
def get_unattached_ebs_volumes(region: str = DEFAULT_REGION) -> List[Dict[str, Any]]:
    """Fetches unattached (available) EBS volumes in the specified region.

    Args:
        region (str): AWS region code (e.g. 'us-east-1').

    Returns:
        List[Dict[str, Any]]: List of dictionary items containing volume details.
    """
    logger.info("Scanning for unattached EBS volumes in region: %s", region)
    unattached_volumes: List[Dict[str, Any]] = []

    try:
        ec2_client = boto3.client("ec2", region_name=region)
        paginator = ec2_client.get_paginator("describe_volumes")
        page_iterator = paginator.paginate(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )

        for page in page_iterator:
            for volume in page.get("Volumes", []):
                unattached_volumes.append(
                    {
                        "volume_id": volume.get("VolumeId"),
                        "size_gb": volume.get("Size"),
                        "volume_type": volume.get("VolumeType"),
                        "create_time": volume.get("CreateTime").isoformat()
                        if volume.get("CreateTime")
                        else "N/A",
                    }
                )

        logger.info("Found %d unattached EBS volume(s).", len(unattached_volumes))
    except (ClientError, BotoCoreError) as err:
        logger.error("Failed to describe EBS volumes in %s: %s", region, str(err))
    except Exception as err:
        logger.exception("Unexpected error while fetching EBS volumes: %s", str(err))

    return unattached_volumes


def get_unattached_eips(region: str = DEFAULT_REGION) -> List[Dict[str, Any]]:
    """Fetches Elastic IP addresses (EIPs) that are not associated with any instance or ENI.

    Args:
        region (str): AWS region code (e.g. 'us-east-1').

    Returns:
        List[Dict[str, Any]]: List of unattached EIP details.
    """
    logger.info("Scanning for unattached Elastic IPs in region: %s", region)
    unattached_eips: List[Dict[str, Any]] = []

    try:
        ec2_client = boto3.client("ec2", region_name=region)
        response = ec2_client.describe_addresses()

        for address in response.get("Addresses", []):
            # Unattached EIPs lack 'AssociationId'
            if "AssociationId" not in address:
                unattached_eips.append(
                    {
                        "public_ip": address.get("PublicIp"),
                        "allocation_id": address.get("AllocationId", "N/A"),
                        "domain": address.get("Domain", "vpc"),
                    }
                )

        logger.info("Found %d unattached Elastic IP(s).", len(unattached_eips))
    except (ClientError, BotoCoreError) as err:
        logger.error("Failed to describe Elastic IPs in %s: %s", region, str(err))
    except Exception as err:
        logger.exception("Unexpected error while fetching Elastic IPs: %s", str(err))

    return unattached_eips


def get_stopped_instances(region: str = DEFAULT_REGION) -> List[Dict[str, Any]]:
    """Fetches EC2 instances that are currently in 'stopped' state.

    Args:
        region (str): AWS region code (e.g. 'us-east-1').

    Returns:
        List[Dict[str, Any]]: List of stopped EC2 instance details.
    """
    logger.info("Scanning for stopped EC2 instances in region: %s", region)
    stopped_instances: List[Dict[str, Any]] = []

    try:
        ec2_client = boto3.client("ec2", region_name=region)
        paginator = ec2_client.get_paginator("describe_instances")
        page_iterator = paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
        )

        for page in page_iterator:
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    # Extract instance name tag if available
                    instance_name = "N/A"
                    for tag in instance.get("Tags", []):
                        if tag.get("Key") == "Name":
                            instance_name = tag.get("Value", "N/A")
                            break

                    stopped_instances.append(
                        {
                            "instance_id": instance.get("InstanceId"),
                            "name": instance_name,
                            "instance_type": instance.get("InstanceType"),
                            "launch_time": instance.get("LaunchTime").isoformat()
                            if instance.get("LaunchTime")
                            else "N/A",
                        }
                    )

        logger.info("Found %d stopped EC2 instance(s).", len(stopped_instances))
    except (ClientError, BotoCoreError) as err:
        logger.error("Failed to describe EC2 instances in %s: %s", region, str(err))
    except Exception as err:
        logger.exception("Unexpected error while fetching stopped EC2 instances: %s", str(err))

    return stopped_instances


def get_estimated_billing() -> Optional[float]:
    """Fetches the latest EstimatedCharges metric from CloudWatch in 'us-east-1'.

    Note: AWS Billing metrics are strictly published to CloudWatch in the 'us-east-1' region.

    Returns:
        Optional[float]: Estimated charge amount in USD, or None if unavailable.
    """
    logger.info("Fetching estimated billing metrics from CloudWatch (us-east-1)...")
    billing_region = "us-east-1"

    try:
        cw_client = boto3.client("cloudwatch", region_name=billing_region)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=2)  # 48 hour window to ensure metric availability

        response = cw_client.get_metric_statistics(
            Namespace="AWS/Billing",
            MetricName="EstimatedCharges",
            Dimensions=[{"Name": "Currency", "Value": "USD"}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,  # 24-hour period
            Statistics=["Maximum"],
        )

        datapoints = response.get("Datapoints", [])
        if datapoints:
            # Sort datapoints by Timestamp descending to get the most recent reading
            sorted_datapoints = sorted(datapoints, key=lambda x: x["Timestamp"], reverse=True)
            latest_charge = float(sorted_datapoints[0].get("Maximum", 0.0))
            logger.info("Latest estimated billing charge: $%.2f USD", latest_charge)
            return latest_charge

        logger.warning("No billing datapoints returned from CloudWatch.")
        return 0.0
    except (ClientError, BotoCoreError) as err:
        logger.error("CloudWatch Billing API error: %s", str(err))
    except Exception as err:
        logger.exception("Unexpected error fetching estimated billing: %s", str(err))

    return None


# ---------------------------------------------------------------------------
# Notification Functions (Zero external dependency using urllib & json)
# ---------------------------------------------------------------------------
def build_telegram_report(
    region: str,
    ebs_volumes: List[Dict[str, Any]],
    eips: List[Dict[str, Any]],
    stopped_instances: List[Dict[str, Any]],
    estimated_billing: Optional[float],
) -> str:
    """Constructs a clean HTML formatted report for Telegram notification.

    Args:
        region (str): AWS region.
        ebs_volumes (List[Dict[str, Any]]): Unattached EBS volumes list.
        eips (List[Dict[str, Any]]): Unattached Elastic IPs list.
        stopped_instances (List[Dict[str, Any]]): Stopped EC2 instances list.
        estimated_billing (Optional[float]): Estimated billing in USD.

    Returns:
        str: Formatted HTML string ready for Telegram API message post.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    billing_str = (
        f"${estimated_billing:.2f} USD" if estimated_billing is not None else "Bilgi Alınamadı"
    )

    total_waste_items = len(ebs_volumes) + len(eips) + len(stopped_instances)

    lines: List[str] = [
        "<b>🛡️ AWS FinOps & Waste Sentinel Report</b>",
        f"<b>Tarih:</b> <code>{now_str}</code>",
        f"<b>Bölge (Region):</b> <code>{region}</code>",
        f"<b>Tahmini Fatura:</b> <code>{billing_str}</code>",
        "----------------------------------------",
    ]

    if total_waste_items == 0:
        lines.append("<b>✅ Tebrikler! Hesabınızda atıl kaynak bulunamadı. (Clean State)</b>")
        return "\n".join(lines)

    lines.append(f"<b>⚠️ Toplam Tespit Edilen Atıl Kaynak: {total_waste_items}</b>\n")

    # 1. Unattached EBS Volumes
    if ebs_volumes:
        lines.append("<b>💾 Bağlı Olmayan EBS Diskleri (Unattached Volumes):</b>")
        for vol in ebs_volumes:
            lines.append(
                f"  • ID: <code>{vol['volume_id']}</code> | Boyut: <b>{vol['size_gb']} GB</b> | Tür: {vol['volume_type']}"
            )
        lines.append("")

    # 2. Unattached Elastic IPs
    if eips:
        lines.append("<b>🌐 Boşta Duran Elastic IP'ler (Unattached EIPs):</b>")
        for eip in eips:
            lines.append(
                f"  • IP: <code>{eip['public_ip']}</code> | Allocation ID: <code>{eip['allocation_id']}</code>"
            )
        lines.append("")

    # 3. Stopped EC2 Instances
    if stopped_instances:
        lines.append("<b>🛑 Durdurulmuş EC2 Sunucuları (Stopped Instances):</b>")
        for inst in stopped_instances:
            lines.append(
                f"  • ID: <code>{inst['instance_id']}</code> | Ad: <b>{inst['name']}</b> | Tür: {inst['instance_type']}"
            )
        lines.append("")

    lines.append("<i>💡 İpucu: Gereksiz maliyetleri önlemek için kullanılmayan kaynakları temizleyin.</i>")

    return "\n".join(lines)


def send_telegram_message(message: str, bot_token: str, chat_id: str) -> bool:
    """Sends an HTML formatted message to Telegram Bot API using standard urllib.

    Args:
        message (str): HTML text content to send.
        bot_token (str): Telegram Bot API token.
        chat_id (str): Destination Telegram Chat ID.

    Returns:
        bool: True if message sent successfully, False otherwise.
    """
    if not bot_token or not chat_id:
        logger.warning(
            "Telegram credentials missing (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). "
            "Skipping notification delivery."
        )
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info("Telegram notification delivered successfully via urllib.")
                return True
            else:
                logger.error("Telegram API returned non-200 status code: %d", response.status)
                return False
    except urllib.error.HTTPError as http_err:
        err_body = http_err.read().decode("utf-8", errors="ignore") if http_err.fp else "N/A"
        logger.error(
            "HTTP error sending Telegram message: Code %d - Reason: %s - Response: %s",
            http_err.code,
            http_err.reason,
            err_body,
        )
    except urllib.error.URLError as url_err:
        logger.error("URL error sending Telegram message: %s", str(url_err.reason))
    except Exception as err:
        logger.exception("Unexpected error sending Telegram message: %s", str(err))

    return False


# ---------------------------------------------------------------------------
# Lambda Main Handler & Local Execution Entry Point
# ---------------------------------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda Handler entry point.

    Args:
        event (Dict[str, Any]): Event data passed to Lambda.
        context (Any): Runtime information context passed to Lambda.

    Returns:
        Dict[str, Any]: Execution summary response payload.
    """
    logger.info("AWS FinOps & Waste Sentinel execution started.")

    region = event.get("region", DEFAULT_REGION) if isinstance(event, dict) else DEFAULT_REGION

    # 1. Execute AWS Scanning Modules
    ebs_volumes = get_unattached_ebs_volumes(region=region)
    eips = get_unattached_eips(region=region)
    stopped_instances = get_stopped_instances(region=region)
    estimated_billing = get_estimated_billing()

    # 2. Build Report
    report_html = build_telegram_report(
        region=region,
        ebs_volumes=ebs_volumes,
        eips=eips,
        stopped_instances=stopped_instances,
        estimated_billing=estimated_billing,
    )

    # 3. Print Report locally to logs
    logger.info("Generated FinOps Report:\n%s", report_html)

    # 4. Dispatch Telegram Notification
    notification_sent = send_telegram_message(
        message=report_html, bot_token=BOT_TOKEN, chat_id=CHAT_ID
    )

    summary = {
        "status": "success",
        "region": region,
        "unattached_ebs_count": len(ebs_volumes),
        "unattached_eip_count": len(eips),
        "stopped_instance_count": len(stopped_instances),
        "estimated_billing_usd": estimated_billing,
        "notification_sent": notification_sent,
    }

    logger.info("AWS FinOps Sentinel execution completed successfully.")
    return {
        "statusCode": 200,
        "body": summary,
    }


if __name__ == "__main__":
    logger.info("Executing AWS FinOps & Waste Sentinel locally...")
    # Mock event and context for local testing
    result = lambda_handler(event={}, context=None)
    print("\nLocal Execution Result Summary:")
    print(result)
