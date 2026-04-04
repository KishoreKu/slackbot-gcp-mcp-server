"""
ScoringService — orchestrates the full scoring pipeline:

  1. Fetch user baseline from Firestore
  2. Run all signals against the transaction
  3. Compute composite risk score
  4. Map score → decision (APPROVE / REVIEW / DECLINE)
  5. Call Gemini to generate plain-English explanation
  6. Return structured ScoringResponse
"""

from __future__ import annotations

import logging
from typing import Optional

from app.models.transaction import (
    Decision,
    ScoringResponse,
    TransactionRequest,
    TriggeredSignal,
)
from app.signals.engine import (
    SignalResult,
    compute_composite_score,
    run_all_signals,
)
from app.services.firestore_client import FirestoreClient
from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

# ── Decision thresholds ───────────────────────────────────────────────────────
# Tune these per customer via config in Phase 2.
# For now: sensible defaults that balance false positives vs coverage.

THRESHOLD_APPROVE = 0.35   # below this → APPROVE
THRESHOLD_REVIEW  = 0.70   # between APPROVE and this → REVIEW, above → DECLINE


class ScoringService:
    def __init__(
        self,
        firestore: FirestoreClient,
        gemini: GeminiClient,
    ):
        self.firestore = firestore
        self.gemini = gemini

    async def score(self, tx: TransactionRequest) -> ScoringResponse:
        # ── 1. Fetch baseline (returns {} if user is new) ─────────────────
        baseline = await self.firestore.get_baseline(tx.user_id)
        logger.info("Baseline fetched for user=%s keys=%s", tx.user_id, list(baseline.keys()))

        # ── 2. Run all signals ────────────────────────────────────────────
        signal_results = run_all_signals(tx, baseline)
        triggered      = [s for s in signal_results if s.triggered]
        logger.info(
            "Signals: %d triggered / %d total for tx=%s",
            len(triggered), len(signal_results), tx.transaction_id,
        )

        # ── 3. Composite score ────────────────────────────────────────────
        risk_score, confidence = compute_composite_score(signal_results)

        # ── 4. Decision ───────────────────────────────────────────────────
        decision = self._map_decision(risk_score)

        # ── 5. Generate explanation ───────────────────────────────────────
        explanation = await self.gemini.explain(tx, triggered, risk_score, decision, baseline)

        # ── 6. Build response ─────────────────────────────────────────────
        triggered_signals = [
            TriggeredSignal(
                signal_id   = s.signal_id,
                label       = s.label,
                score_delta = s.score_delta,
                severity    = s.severity,
            )
            for s in triggered
        ]
        # Sort by contribution descending for the response
        triggered_signals.sort(key=lambda s: s.score_delta, reverse=True)

        return ScoringResponse(
            transaction_id = tx.transaction_id,
            user_id        = tx.user_id,
            risk_score     = risk_score,
            confidence     = confidence,
            decision       = decision,
            explanation    = explanation,
            signals        = triggered_signals,
        )

    @staticmethod
    def _map_decision(score: float) -> Decision:
        if score < THRESHOLD_APPROVE:
            return Decision.APPROVE
        if score < THRESHOLD_REVIEW:
            return Decision.REVIEW
        return Decision.DECLINE
