"""
Signal Engine — 15 weighted anomaly signals.

Each signal is a pure function:
    (tx: TransactionRequest, baseline: dict) -> SignalResult

Signals are composited by the ScoringService using a weighted sum,
then clamped to [0, 1].

Adding a new signal: implement the function, add it to SIGNAL_REGISTRY.
No other files need to change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from app.models.transaction import TransactionRequest


@dataclass
class SignalResult:
    signal_id: str
    label: str
    triggered: bool
    score_delta: float
    severity: str = "low"
    detail: str = ""


HIGH_RISK_CATEGORIES = {
    "CRYPTO",
    "GAMBLING",
    "WIRE",
    "FOREX",
    "MONEY_SERVICE",
    "CASH_ADVANCE",
    "PAWN",
    "ADULT",
    "MARIJUANA",
}

MEDIUM_RISK_CATEGORIES = {
    "ACH_TRANSFER",
    "P2P",
    "GIFT_CARD",
    "PRECIOUS_METALS",
    "INTERNATIONAL_WIRE",
}


def signal_amount_velocity(tx: TransactionRequest, baseline: dict) -> SignalResult:
    avg = baseline.get("avg_transaction_amount", 0)
    if avg <= 0:
        return SignalResult(
            "amount_velocity_spike",
            "Amount velocity spike",
            False,
            0.0,
            detail="no baseline",
        )

    ratio = tx.amount / avg
    if ratio >= 10:
        return SignalResult(
            "amount_velocity_spike",
            "Amount velocity spike",
            True,
            0.55,
            severity="high",
            detail=f"{ratio:.1f}× user's avg (${avg:.2f})",
        )
    if ratio >= 5:
        return SignalResult(
            "amount_velocity_spike",
            "Amount velocity spike",
            True,
            0.35,
            severity="medium",
            detail=f"{ratio:.1f}× user's avg (${avg:.2f})",
        )
    if ratio >= 3:
        return SignalResult(
            "amount_velocity_spike",
            "Amount velocity spike",
            True,
            0.15,
            severity="low",
            detail=f"{ratio:.1f}× user's avg (${avg:.2f})",
        )
    return SignalResult("amount_velocity_spike", "Amount velocity spike", False, 0.0)


def signal_new_merchant(tx: TransactionRequest, baseline: dict) -> SignalResult:
    known = set(baseline.get("known_merchants", []))
    if not known:
        return SignalResult(
            "new_merchant", "New merchant", False, 0.0, detail="no baseline"
        )
    name = tx.merchant.name.lower().strip()
    is_new = not any(name in k.lower() for k in known)
    if is_new:
        return SignalResult(
            "new_merchant",
            "New merchant",
            True,
            0.12,
            severity="low",
            detail=f"'{tx.merchant.name}' not in {len(known)} known merchants",
        )
    return SignalResult("new_merchant", "New merchant", False, 0.0)


def signal_new_merchant_category(
    tx: TransactionRequest, baseline: dict
) -> SignalResult:
    known_cats = set(c.upper() for c in baseline.get("known_merchant_categories", []))
    cat = tx.merchant.category.upper()
    if known_cats and cat not in known_cats:
        return SignalResult(
            "new_merchant_category",
            "New merchant category",
            True,
            0.10,
            severity="low",
            detail=f"Category '{cat}' first seen for this user",
        )
    return SignalResult("new_merchant_category", "New merchant category", False, 0.0)


def signal_high_risk_category(tx: TransactionRequest, baseline: dict) -> SignalResult:
    cat = tx.merchant.category.upper()
    if cat in HIGH_RISK_CATEGORIES:
        return SignalResult(
            "high_risk_category",
            "High-risk merchant category",
            True,
            0.25,
            severity="high",
            detail=f"Category '{cat}' is high-risk",
        )
    if cat in MEDIUM_RISK_CATEGORIES:
        return SignalResult(
            "high_risk_category",
            "High-risk merchant category",
            True,
            0.12,
            severity="medium",
            detail=f"Category '{cat}' is medium-risk",
        )
    return SignalResult("high_risk_category", "High-risk merchant category", False, 0.0)


def signal_geo_mismatch(tx: TransactionRequest, baseline: dict) -> SignalResult:
    if not tx.device or not tx.card:
        return SignalResult(
            "geo_mismatch",
            "Geo mismatch",
            False,
            0.0,
            detail="insufficient device/card data",
        )
    card_country = (tx.card.card_country or "").upper()
    device_country = (tx.device.geo_country or "").upper()
    if card_country and device_country and card_country != device_country:
        return SignalResult(
            "geo_mismatch",
            "Geo mismatch",
            True,
            0.30,
            severity="high",
            detail=f"Card country {card_country} ≠ IP country {device_country}",
        )
    return SignalResult("geo_mismatch", "Geo mismatch", False, 0.0)


def signal_new_country(tx: TransactionRequest, baseline: dict) -> SignalResult:
    known_countries = set(c.upper() for c in baseline.get("known_countries", []))
    merchant_country = (tx.merchant.country or "").upper()
    device_country = (tx.device.geo_country or "").upper() if tx.device else ""
    country = merchant_country or device_country
    if known_countries and country and country not in known_countries:
        return SignalResult(
            "new_country",
            "New country",
            True,
            0.20,
            severity="medium",
            detail=f"Country '{country}' not in user's history",
        )
    return SignalResult("new_country", "New country", False, 0.0)


def signal_vpn_tor(tx: TransactionRequest, baseline: dict) -> SignalResult:
    if not tx.device:
        return SignalResult("vpn_tor_proxy", "VPN/Tor/Proxy", False, 0.0)
    is_anon = tx.device.is_vpn or tx.device.is_tor or tx.device.is_proxy
    if is_anon:
        label = "Tor" if tx.device.is_tor else ("VPN" if tx.device.is_vpn else "Proxy")
        return SignalResult(
            "vpn_tor_proxy",
            "VPN/Tor/Proxy",
            True,
            0.25,
            severity="medium",
            detail=f"Device is using {label}",
        )
    return SignalResult("vpn_tor_proxy", "VPN/Tor/Proxy", False, 0.0)


def signal_new_device(tx: TransactionRequest, baseline: dict) -> SignalResult:
    if not tx.device or not tx.device.device_id:
        return SignalResult("new_device", "New device", False, 0.0)
    known_devices = set(baseline.get("known_devices", []))
    if known_devices and tx.device.device_id not in known_devices:
        return SignalResult(
            "new_device",
            "New device",
            True,
            0.18,
            severity="medium",
            detail=f"Device '{tx.device.device_id}' not in {len(known_devices)} known devices",
        )
    return SignalResult("new_device", "New device", False, 0.0)


def signal_unusual_hour(tx: TransactionRequest, baseline: dict) -> SignalResult:
    typical_hours = set(baseline.get("typical_hours", []))
    if not typical_hours or not tx.timestamp:
        return SignalResult("unusual_hour", "Unusual hour", False, 0.0)
    hour = tx.timestamp.hour
    if hour not in typical_hours:
        return SignalResult(
            "unusual_hour",
            "Unusual hour",
            True,
            0.08,
            severity="low",
            detail=f"Transaction at {hour:02d}:00 outside typical activity window",
        )
    return SignalResult("unusual_hour", "Unusual hour", False, 0.0)


def signal_daily_spend_limit(tx: TransactionRequest, baseline: dict) -> SignalResult:
    avg_daily = baseline.get("avg_daily_spend", 0)
    spend_today = baseline.get("spend_today", 0)
    if avg_daily <= 0:
        return SignalResult("daily_spend_exceeded", "Daily spend spike", False, 0.0)
    projected = spend_today + tx.amount
    ratio = projected / avg_daily
    if ratio >= 5:
        return SignalResult(
            "daily_spend_exceeded",
            "Daily spend spike",
            True,
            0.30,
            severity="high",
            detail=f"Projected daily spend ${projected:.2f} is {ratio:.1f}× avg (${avg_daily:.2f})",
        )
    if ratio >= 3:
        return SignalResult(
            "daily_spend_exceeded",
            "Daily spend spike",
            True,
            0.15,
            severity="medium",
            detail=f"Projected daily spend ${projected:.2f} is {ratio:.1f}× avg (${avg_daily:.2f})",
        )
    return SignalResult("daily_spend_exceeded", "Daily spend spike", False, 0.0)


def signal_rapid_succession(tx: TransactionRequest, baseline: dict) -> SignalResult:
    count_24h = baseline.get("transaction_count_24h", 0)
    avg_30d_daily = (
        baseline.get("transaction_count_30d", 0) / 30
        if baseline.get("transaction_count_30d")
        else 0
    )
    if avg_30d_daily <= 0:
        return SignalResult("rapid_succession", "Rapid succession", False, 0.0)
    ratio = (count_24h + 1) / (avg_30d_daily + 1)
    if ratio >= 4:
        return SignalResult(
            "rapid_succession",
            "Rapid succession",
            True,
            0.35,
            severity="high",
            detail=f"{count_24h} tx in 24h vs avg {avg_30d_daily:.1f}/day — possible card testing",
        )
    if ratio >= 2:
        return SignalResult(
            "rapid_succession",
            "Rapid succession",
            True,
            0.15,
            severity="medium",
            detail=f"{count_24h} tx in 24h vs avg {avg_30d_daily:.1f}/day",
        )
    return SignalResult("rapid_succession", "Rapid succession", False, 0.0)


def signal_new_user(tx: TransactionRequest, baseline: dict) -> SignalResult:
    count = baseline.get("transaction_count_90d", 0)
    if count < 3:
        return SignalResult(
            "new_user",
            "New user — thin history",
            True,
            0.15,
            severity="medium",
            detail=f"Only {count} transactions in 90 days",
        )
    return SignalResult("new_user", "New user — thin history", False, 0.0)


def signal_prior_high_risk(tx: TransactionRequest, baseline: dict) -> SignalResult:
    flags = baseline.get("high_risk_flags", 0)
    if flags >= 3:
        return SignalResult(
            "prior_high_risk",
            "Prior high-risk history",
            True,
            0.25,
            severity="high",
            detail=f"User has {flags} prior high-risk transaction flags",
        )
    if flags >= 1:
        return SignalResult(
            "prior_high_risk",
            "Prior high-risk history",
            True,
            0.10,
            severity="low",
            detail=f"User has {flags} prior high-risk transaction flag(s)",
        )
    return SignalResult("prior_high_risk", "Prior high-risk history", False, 0.0)


def signal_prepaid_card(tx: TransactionRequest, baseline: dict) -> SignalResult:
    if tx.card and tx.card.is_prepaid:
        return SignalResult(
            "prepaid_card",
            "Prepaid card",
            True,
            0.12,
            severity="low",
            detail="Prepaid cards have higher fraud correlation",
        )
    return SignalResult("prepaid_card", "Prepaid card", False, 0.0)


def signal_large_round_amount(tx: TransactionRequest, baseline: dict) -> SignalResult:
    amount = tx.amount
    is_round = (amount % 100 == 0) and amount >= 1000
    if is_round:
        return SignalResult(
            "large_round_amount",
            "Large round amount",
            True,
            0.08,
            severity="low",
            detail=f"${amount:,.2f} is a large round number",
        )
    return SignalResult("large_round_amount", "Large round amount", False, 0.0)


SIGNAL_REGISTRY: list[tuple[str, Callable, float]] = [
    ("amount_velocity_spike", signal_amount_velocity, 1.0),
    ("geo_mismatch", signal_geo_mismatch, 1.0),
    ("rapid_succession", signal_rapid_succession, 1.0),
    ("daily_spend_exceeded", signal_daily_spend_limit, 0.9),
    ("high_risk_category", signal_high_risk_category, 0.9),
    ("vpn_tor_proxy", signal_vpn_tor, 0.85),
    ("new_country", signal_new_country, 0.80),
    ("new_device", signal_new_device, 0.75),
    ("prior_high_risk", signal_prior_high_risk, 0.75),
    ("new_user", signal_new_user, 0.65),
    ("new_merchant", signal_new_merchant, 0.50),
    ("new_merchant_category", signal_new_merchant_category, 0.45),
    ("unusual_hour", signal_unusual_hour, 0.40),
    ("prepaid_card", signal_prepaid_card, 0.35),
    ("large_round_amount", signal_large_round_amount, 0.25),
]


def run_all_signals(tx: TransactionRequest, baseline: dict) -> list[SignalResult]:
    results = []
    for name, fn, weight in SIGNAL_REGISTRY:
        result = fn(tx, baseline)
        result.score_delta = round(result.score_delta * weight, 4)
        results.append(result)
    return results


def compute_composite_score(signal_results: list[SignalResult]) -> tuple[float, float]:
    triggered = [s for s in signal_results if s.triggered]
    if not triggered:
        return 0.05, 0.95

    raw_sum = sum(s.score_delta for s in triggered)

    risk_score = 1 / (1 + math.exp(-3.5 * (raw_sum - 0.5)))
    risk_score = round(min(max(risk_score, 0.01), 0.99), 4)

    n_triggered = len(triggered)
    confidence = round(min(0.5 + (n_triggered * 0.08), 0.98), 4)

    return risk_score, confidence
