"""Notification dispatcher for supplier risk alerts.

Supports email (aiosmtplib) and webhook (async HTTP + HMAC-SHA256).
All errors are caught and logged — never blocking.
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import aiosmtplib
except ImportError:
    aiosmtplib = None

try:
    import httpx
except ImportError:
    httpx = None

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskNotificationChannel


logger = logging.getLogger(__name__)


class SSRFError(Exception):
    """Raised when a webhook URL points to a private/internal address."""
    pass


def _get_fernet() -> Optional[Fernet]:
    key = os.environ.get("RISK_ENCRYPTION_KEY")
    if not key or Fernet is None:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("Invalid RISK_ENCRYPTION_KEY")
        return None


def encrypt_secret(secret: str) -> str:
    """Encrypt a webhook secret before storage. Raises if encryption unavailable."""
    fernet = _get_fernet()
    if fernet is None:
        raise RuntimeError("RISK_ENCRYPTION_KEY not configured: cannot store webhook secret")
    return fernet.encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a stored webhook secret."""
    fernet = _get_fernet()
    if fernet is None:
        return token
    try:
        return fernet.decrypt(token.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt webhook secret")
        return token


def _is_private_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return True
    lower = hostname.lower()
    if lower in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    except ValueError:
        # hostname is not an IP address; not private by IP check
        pass
    return False


def _sign_payload(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _alert_to_dict(alert: SupplierRiskAlert) -> dict:
    return {
        "alert_id": str(alert.alert_id),
        "supplier_id": str(alert.supplier_id),
        "risk_level": alert.risk_level,
        "risk_score": alert.risk_score,
        "quality_score": alert.quality_score,
        "delivery_score": alert.delivery_score,
        "compliance_score": alert.compliance_score,
        "status": alert.status,
        "snapshot_date": alert.snapshot_date.isoformat(),
        "product_line_code": alert.product_line_code,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


async def _send_email(channel: SupplierRiskNotificationChannel, alert: SupplierRiskAlert) -> None:
    if aiosmtplib is None:
        logger.warning("aiosmtplib not installed; skipping email notification")
        return

    config = channel.config or {}
    addresses = config.get("addresses") or []
    if not addresses:
        return

    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    subject = f"供应商风险预警 [{alert.risk_level.upper()}] {alert.snapshot_date}"
    body = (
        f"供应商风险等级: {alert.risk_level}\n"
        f"风险分: {alert.risk_score}\n"
        f"质量分: {alert.quality_score}\n"
        f"交付分: {alert.delivery_score}\n"
        f"合规分: {alert.compliance_score}\n"
        f"快照日期: {alert.snapshot_date}\n"
        f"查看详情: /supplier-risk/alerts/{alert.alert_id}\n"
    )

    try:
        await aiosmtplib.send(
            message=f"Subject: {subject}\n\n{body}",
            recipients=addresses,
            sender=smtp_user or "noreply@openqms.local",
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            start_tls=True,
        )
        logger.info("Sent email notification for alert %s", alert.alert_id)
    except Exception as e:
        logger.error("Email notification failed for alert %s: %s", alert.alert_id, e)


async def _send_webhook(channel: SupplierRiskNotificationChannel, alert: SupplierRiskAlert) -> None:
    if httpx is None:
        logger.warning("httpx not installed; skipping webhook notification")
        return

    config = channel.config or {}
    url = config.get("url", "")
    if not url:
        return

    if _is_private_url(url):
        raise SSRFError(f"Webhook URL points to private address: {url}")

    secret = decrypt_secret(config.get("secret_encrypted", ""))
    payload = json.dumps(_alert_to_dict(alert), ensure_ascii=False).encode()
    signature = _sign_payload(secret, payload)

    headers = {
        "Content-Type": "application/json",
        "X-Signature": signature,
    }

    last_error = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, content=payload, headers=headers)
                response.raise_for_status()
            logger.info("Sent webhook notification for alert %s", alert.alert_id)
            return
        except Exception as e:
            last_error = e
            logger.warning("Webhook attempt %d failed for alert %s: %s", attempt + 1, alert.alert_id, e)

    if last_error:
        logger.error("Webhook notification failed for alert %s after retries: %s", alert.alert_id, last_error)


def sanitize_channel_config(config: dict) -> dict:
    """Return a copy of channel config with secrets redacted for API responses."""
    safe = dict(config)
    if "secret_encrypted" in safe:
        safe["secret_encrypted"] = "***"
    if "secret" in safe:
        safe["secret"] = "***"
    return safe


async def send_notifications(
    db: AsyncSession,
    alert: SupplierRiskAlert,
    product_line_code: Optional[str] = None,
) -> None:
    """Send notifications for an alert via all matching enabled channels.

    Queries channels where:
    - enabled is True
    - channel's min_risk_level <= alert.risk_level
    - channel matches product_line_code or global
    """
    level_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    alert_level = level_order.get(alert.risk_level, 0)

    query = select(SupplierRiskNotificationChannel).where(
        SupplierRiskNotificationChannel.enabled.is_(True)
    )

    result = await db.execute(query)
    channels = list(result.scalars().all())

    for channel in channels:
        channel_level = level_order.get(channel.min_risk_level, 0)
        if channel_level > alert_level:
            continue

        # Product line matching: if channel has a PL set, it must match
        if channel.product_line_code and channel.product_line_code != product_line_code:
            continue

        try:
            if channel.channel_type == "email":
                await _send_email(channel, alert)
            elif channel.channel_type == "webhook":
                await _send_webhook(channel, alert)
        except Exception as e:
            logger.error("Notification dispatch failed for channel %s: %s", channel.channel_id, e)
