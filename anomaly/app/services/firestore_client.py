"""
FirestoreClient — manages user behavioral baselines.

Collection: `user_baselines`
Document ID: user_id

Baseline is updated by a scheduled Cloud Run Job (not the hot path).
On the hot path we only READ — baseline writes happen async.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

COLLECTION = "user_baselines"

EMPTY_BASELINE: dict = {
    "avg_transaction_amount": 0.0,
    "p95_transaction_amount": 0.0,
    "max_transaction_amount": 0.0,
    "transaction_count_90d": 0,
    "transaction_count_30d": 0,
    "transaction_count_24h": 0,
    "known_merchants": [],
    "known_countries": [],
    "known_devices": [],
    "known_merchant_categories": [],
    "typical_hours": [],
    "typical_days": [],
    "avg_daily_spend": 0.0,
    "spend_today": 0.0,
    "spend_this_week": 0.0,
    "last_transaction_at": None,
    "high_risk_flags": 0,
}


class FirestoreClient:
    def __init__(self):
        self._db = firestore.AsyncClient()

    async def get_baseline(self, user_id: str) -> dict:
        try:
            doc_ref = self._db.collection(COLLECTION).document(user_id)
            doc = await doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                logger.debug("Baseline found for user=%s", user_id)
                return {**EMPTY_BASELINE, **data}
            logger.info("No baseline for user=%s — returning empty", user_id)
            return dict(EMPTY_BASELINE)
        except Exception as e:
            logger.warning("Firestore read failed for user=%s: %s", user_id, e)
            return dict(EMPTY_BASELINE)

    async def increment_24h_count(self, user_id: str) -> None:
        try:
            doc_ref = self._db.collection(COLLECTION).document(user_id)
            await doc_ref.set(
                {"transaction_count_24h": firestore.Increment(1)},
                merge=True,
            )
        except Exception as e:
            logger.warning("Failed to increment 24h count for user=%s: %s", user_id, e)

    async def flag_high_risk(self, user_id: str) -> None:
        try:
            doc_ref = self._db.collection(COLLECTION).document(user_id)
            await doc_ref.set(
                {"high_risk_flags": firestore.Increment(1)},
                merge=True,
            )
        except Exception as e:
            logger.warning("Failed to flag high-risk for user=%s: %s", user_id, e)

    async def refresh_baseline(self, user_id: str) -> None:
        logger.info("refresh_baseline called for user=%s (stub)", user_id)

    async def upsert_baseline(self, user_id: str, data: dict) -> None:
        try:
            doc_ref = self._db.collection(COLLECTION).document(user_id)
            await doc_ref.set(data, merge=True)
            logger.info("Baseline upserted for user=%s", user_id)
        except Exception as e:
            logger.error("Failed to upsert baseline for user=%s: %s", user_id, e)
            raise
