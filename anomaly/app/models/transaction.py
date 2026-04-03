"""
Data models for transaction scoring.
All fields are validated by Pydantic before any scoring logic runs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────────────────────────


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    DECLINE = "DECLINE"


class TransactionType(str, Enum):
    CARD_PRESENT = "CARD_PRESENT"
    CARD_NOT_PRESENT = "CARD_NOT_PRESENT"
    ACH_TRANSFER = "ACH_TRANSFER"
    WIRE = "WIRE"
    CRYPTO = "CRYPTO"
    P2P = "P2P"
    SUBSCRIPTION = "SUBSCRIPTION"
    ATM = "ATM"


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    JPY = "JPY"


# ── Sub-models ───────────────────────────────────────────────────────────────


class Merchant(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., description="MCC code or category slug")
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2")
    mcc_code: Optional[str] = Field(None, description="Raw 4-digit MCC")


class DeviceInfo(BaseModel):
    device_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    geo_country: Optional[str] = None  # derived from IP
    geo_city: Optional[str] = None
    is_vpn: Optional[bool] = None
    is_tor: Optional[bool] = None
    is_proxy: Optional[bool] = None
    os: Optional[str] = None
    fingerprint_hash: Optional[str] = None


class CardInfo(BaseModel):
    last_four: Optional[str] = None
    card_country: Optional[str] = None  # issuing country
    card_network: Optional[str] = None  # VISA / MC / AMEX
    is_prepaid: Optional[bool] = None
    is_corporate: Optional[bool] = None


# ── Main request ─────────────────────────────────────────────────────────────


class TransactionRequest(BaseModel):
    # Required identity
    transaction_id: str = Field(..., description="Your system's unique tx ID")
    user_id: str = Field(..., description="Your internal user identifier")

    # Required financials
    amount: float = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(default="USD")

    # Required context
    transaction_type: TransactionType = Field(default=TransactionType.CARD_NOT_PRESENT)
    merchant: Merchant

    # Optional enrichment (more = better accuracy)
    device: Optional[DeviceInfo] = None
    card: Optional[CardInfo] = None
    timestamp: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        description="Transaction time (UTC). Defaults to now if omitted.",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Any extra key-value pairs you want logged and passed to the model",
    )

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: float) -> float:
        return round(v, 2)

    @model_validator(mode="after")
    def validate_geo_consistency(self) -> "TransactionRequest":
        """Warn (don't block) if card country and device geo differ."""
        if self.card and self.device:
            cc = self.card.card_country
            gc = self.device.geo_country
            if cc and gc and cc != gc:
                if self.metadata is None:
                    self.metadata = {}
                self.metadata["_geo_mismatch_detected"] = True
        return self


# ── Response ─────────────────────────────────────────────────────────────────


class TriggeredSignal(BaseModel):
    signal_id: str = Field(..., description="Machine-readable signal slug")
    label: str = Field(..., description="Human-readable label")
    score_delta: float = Field(
        ..., description="How much this signal contributed (0–1)"
    )
    severity: str = Field(..., description="low | medium | high")


class ScoringResponse(BaseModel):
    # Identity echo
    transaction_id: str
    user_id: str

    # Core outputs
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Composite risk score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence")
    decision: Decision

    # Explainability — the key differentiator
    explanation: str = Field(
        ..., description="Plain-English explanation for fraud ops teams"
    )

    # Signal detail
    signals: list[TriggeredSignal] = Field(default_factory=list)

    # Meta
    latency_ms: Optional[float] = None
    model_version: str = Field(default="anomaly-v1")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
