"""Shared tenant-schema resolver for non-agent routes.

Mirrors backend/app/api/dashboard.py's _tenant_schema and
backend/app/api/agent/sessions.py:17's取法 — extracted here so dashboard
and fmea routes share one implementation.
"""
from __future__ import annotations

from starlette.requests import Request


def tenant_schema(request: Request) -> str:
    """Return the per-request tenant schema_name, or 'public' when no tenant."""
    tenant = getattr(request.state, "tenant", None)
    return tenant.schema_name if tenant else "public"
