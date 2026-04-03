"""
GeminiClient — wraps Vertex AI Gemini Flash for explanation generation.

The explanation is the core differentiator of Anomaly.
Prompt engineering here is as important as the signal weights.
"""

from __future__ import annotations

import logging
import os

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from app.models.transaction import Decision, TransactionRequest
from app.signals.engine import SignalResult

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "slb-ai-agent-prod")
REGION = os.environ.get("GCP_REGION", "us-central1")
MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-002")

_SYSTEM_PROMPT = """
You are the explanation engine for Anomaly, a transaction fraud detection API
used by fintech fraud operations teams.

Your job is to write a single clear, factual paragraph (2-4 sentences) that
explains WHY a transaction was flagged, in plain English that a fraud analyst
can read and act on immediately — without needing to understand machine learning.

Rules:
- Be specific: cite actual numbers, ratios, and data points from the signals.
- Do NOT use jargon like "anomaly score", "ML model", "feature vector".
- Do NOT say "the algorithm detected" — describe the actual behaviour.
- End with a concrete recommended action (approve, review, request step-up auth, decline).
- Keep it under 80 words.
- Write in third-person ("This transaction...", "The user...").
- Never fabricate data not present in the signals.
""".strip()


class GeminiClient:
    def __init__(self):
        vertexai.init(project=PROJECT_ID, location=REGION)
        self._model = GenerativeModel(
            MODEL_ID,
            system_instruction=_SYSTEM_PROMPT,
        )
        self._gen_config = GenerationConfig(
            temperature=0.2,
            max_output_tokens=200,
            top_p=0.8,
        )

    async def explain(
        self,
        tx: TransactionRequest,
        triggered_signals: list[SignalResult],
        risk_score: float,
        decision: Decision,
        baseline: dict,
    ) -> str:
        if not triggered_signals:
            return (
                f"This {tx.merchant.category} transaction of "
                f"${tx.amount:,.2f} at {tx.merchant.name} is consistent with "
                f"the user's normal spending patterns. No anomalies detected. Approve."
            )

        prompt = self._build_prompt(
            tx, triggered_signals, risk_score, decision, baseline
        )

        try:
            response = await self._model.generate_content_async(
                prompt,
                generation_config=self._gen_config,
            )
            explanation = response.text.strip()
            logger.info("Gemini explanation generated (%d chars)", len(explanation))
            return explanation

        except Exception as e:
            logger.warning("Gemini call failed, using fallback: %s", e)
            return self._fallback_explanation(tx, triggered_signals, decision)

    def _build_prompt(
        self,
        tx: TransactionRequest,
        triggered: list[SignalResult],
        risk_score: float,
        decision: Decision,
        baseline: dict,
    ) -> str:
        signal_lines = "\n".join(
            f"  - {s.label} [{s.severity.upper()}]: {s.detail}"
            for s in sorted(triggered, key=lambda x: x.score_delta, reverse=True)
        )

        device_ctx = ""
        if tx.device:
            device_ctx = (
                f"Device: {tx.device.os or 'unknown OS'}, "
                f"IP country: {tx.device.geo_country or 'unknown'}, "
                f"VPN: {tx.device.is_vpn}, Tor: {tx.device.is_tor}"
            )

        card_ctx = ""
        if tx.card:
            card_ctx = (
                f"Card country: {tx.card.card_country or 'unknown'}, "
                f"Network: {tx.card.card_network or 'unknown'}, "
                f"Prepaid: {tx.card.is_prepaid}"
            )

        return f"""
TRANSACTION CONTEXT
-------------------
Transaction ID : {tx.transaction_id}
Amount         : ${tx.amount:,.2f} {tx.currency}
Merchant       : {tx.merchant.name} ({tx.merchant.category})
Type           : {tx.transaction_type}
{device_ctx}
{card_ctx}

USER BASELINE (90-day history)
------------------------------
Average transaction amount : ${baseline.get("avg_transaction_amount", 0):,.2f}
P95 transaction amount     : ${baseline.get("p95_transaction_amount", 0):,.2f}
Transactions in 90 days    : {baseline.get("transaction_count_90d", 0)}
Transactions in last 24h   : {baseline.get("transaction_count_24h", 0)}
Avg daily spend            : ${baseline.get("avg_daily_spend", 0):,.2f}
Spend today so far         : ${baseline.get("spend_today", 0):,.2f}
Prior high-risk flags      : {baseline.get("high_risk_flags", 0)}

TRIGGERED SIGNALS (risk score: {risk_score:.2f})
-------------------------------------------------
{signal_lines}

DECISION: {decision.value}

Write the explanation paragraph now:
""".strip()

    @staticmethod
    def _fallback_explanation(
        tx: TransactionRequest,
        triggered: list[SignalResult],
        decision: Decision,
    ) -> str:
        top = sorted(triggered, key=lambda s: s.score_delta, reverse=True)[:3]
        reasons = "; ".join(s.detail for s in top if s.detail)
        action = {
            Decision.APPROVE: "Transaction approved.",
            Decision.REVIEW: "Recommend manual review before proceeding.",
            Decision.DECLINE: "Recommend declining and notifying the customer.",
        }[decision]
        return (
            f"This ${tx.amount:,.2f} transaction at {tx.merchant.name} "
            f"was flagged due to: {reasons}. {action}"
        )
