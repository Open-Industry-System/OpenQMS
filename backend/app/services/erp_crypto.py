"""ERP credential encryption and security utilities.

Provides:
- SHA-256 API Key hashing (inbound)
- Fernet symmetric encryption (outbound credentials)
- Config sanitization for API responses
"""

import hashlib
import hmac
import os

from cryptography.fernet import Fernet

# ---- Fernet singleton ----
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazy-initialize Fernet from ERP_ENCRYPTION_KEY env var."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("ERP_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "ERP_ENCRYPTION_KEY environment variable is not set. "
                "It must be a 32-byte base64-encoded Fernet key."
            )
        _fernet = Fernet(key.encode("utf-8"))
    return _fernet


# ---- API Key hash (inbound) ----
def hash_api_key(api_key: str) -> str:
    """SHA-256 hash of plaintext API Key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """Verify plaintext API Key against stored hash using hmac.compare_digest (timing-safe)."""
    computed = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, api_key_hash)


# ---- Fernet encryption (outbound credentials) ----
def encrypt_credential(plaintext: str) -> str:
    """Encrypt outbound credential."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt outbound credential. Only called at runtime during push_quality_event."""
    fernet = _get_fernet()
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---- Response sanitization ----
def sanitize_config(config: dict) -> dict:
    """Sanitize config for API responses.

    Only typed, allowlisted business settings are returned. Legacy unsafe URL
    fields and unknown or credential-bearing nested fields are omitted.
    """
    from app.schemas.erp import RESTConfig, RESTEndpointConfig

    # Parse each field separately so legacy invalid fields can be omitted while
    # preserving the valid business settings. Pydantic drops unknown nested keys.
    sanitized = {}
    for key in ("base_url", "timeout", "retry", "auth_type"):
        if key not in config:
            continue
        try:
            candidate = {"base_url": "https://redacted.invalid", key: config[key]}
            parsed = RESTConfig.model_validate(candidate)
            sanitized[key] = parsed.model_dump(exclude_none=True).get(key)
        except (ValueError, TypeError):
            continue
    endpoints = {}
    raw_endpoints = config.get("endpoints")
    if isinstance(raw_endpoints, dict):
        known_endpoints = {"suppliers", "customers", "materials", "locations", "purchase_orders",
                           "sales_orders", "inventory_balances", "shipments", "cost_records", "push_event"}
        for name, endpoint in raw_endpoints.items():
            if name not in known_endpoints:
                continue
            try:
                endpoints[name] = RESTEndpointConfig.model_validate(endpoint).model_dump(exclude_none=True)
            except (ValueError, TypeError):
                continue
    sanitized["endpoints"] = endpoints
    # Mapping targets are actual business columns, not arbitrary secret fields.
    from app.models.erp import (ERPSupplier, ERPCustomer, ERPMaterial, ERPLocation,
                                ERPPurchaseOrder, ERPSalesOrder, ERPInventoryBalance,
                                ERPShipment, ERPCostRecord)
    mapping_targets = {column.name for model in (ERPSupplier, ERPCustomer, ERPMaterial, ERPLocation,
                       ERPPurchaseOrder, ERPSalesOrder, ERPInventoryBalance, ERPShipment, ERPCostRecord)
                       for column in model.__table__.columns}
    mapping = config.get("field_mapping")
    if isinstance(mapping, dict):
        sanitized["field_mapping"] = {key: value for key, value in mapping.items()
                                      if key in mapping_targets and isinstance(value, str)}
    return sanitized
