"""
API key authentication middleware.

Phase 1: Keys stored in Secret Manager, validated in memory after cold start.
Phase 2: Move to API Gateway which handles this before Cloud Run is hit.
"""

from __future__ import annotations

import logging
import os

from fastapi import Header, HTTPException, status
from google.cloud import secretmanager

logger = logging.getLogger(__name__)

PROJECT_ID  = os.environ.get("GCP_PROJECT_ID", "your-project-id")
SECRET_NAME = os.environ.get("API_KEYS_SECRET", "anomaly-api-keys")

# Loaded once at startup, refreshed every 5 min in Phase 2
_valid_keys: set[str] = set()
_keys_loaded = False


def _load_keys() -> None:
    """Pull API keys from Secret Manager and cache in memory."""
    global _valid_keys, _keys_loaded
    try:
        client = secretmanager.SecretManagerServiceClient()
        name   = f"projects/{PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        resp   = client.access_secret_version(request={"name": name})
        raw    = resp.payload.data.decode("utf-8")
        # Format: one key per line, lines starting with # are comments
        keys = {
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.startswith("#")
        }
        _valid_keys = keys
        _keys_loaded = True
        logger.info("Loaded %d API keys from Secret Manager", len(keys))
    except Exception as e:
        logger.warning("Could not load API keys from Secret Manager: %s", e)
        # Fallback: allow a dev key from env for local testing
        dev_key = os.environ.get("DEV_API_KEY")
        if dev_key:
            _valid_keys = {dev_key}
            logger.warning("Using DEV_API_KEY fallback — not for production")


async def verify_api_key(
    authorization: str = Header(..., description="Bearer <api_key>"),
) -> str:
    """FastAPI dependency — validates Bearer token against allowed keys."""
    global _keys_loaded
    if not _keys_loaded:
        _load_keys()

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <api_key>'",
        )

    key = authorization.removeprefix("Bearer ").strip()

    if key not in _valid_keys:
        logger.warning("Invalid API key attempt: %s...", key[:8])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return key
