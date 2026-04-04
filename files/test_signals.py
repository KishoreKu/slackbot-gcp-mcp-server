"""
Tests for the signal engine.

Run with: pytest tests/test_signals.py -v
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.models.transaction import (
    CardInfo,
    DeviceInfo,
    Merchant,
    TransactionRequest,
    TransactionType,
)
from app.signals.engine import (
    compute_composite_score,
    run_all_signals,
    signal_amount_velocity,
    signal_daily_spend_limit,
    signal_geo_mismatch,
    signal_high_risk_category,
    signal_new_device,
    signal_new_merchant,
    signal_new_user,
    signal_prior_high_risk,
    signal_rapid_succession,
    signal_vpn_tor,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_tx(**overrides) -> TransactionRequest:
    defaults = dict(
        transaction_id = "txn_test_001",
        user_id        = "usr_test",
        amount         = 50.00,
        currency       = "USD",
        transaction_type = TransactionType.CARD_NOT_PRESENT,
        merchant       = Merchant(name="Starbucks", category="FOOD_BEVERAGE"),
        timestamp      = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return TransactionRequest(**defaults)


def normal_baseline() -> dict:
    return {
        "avg_transaction_amount":    45.00,
        "p95_transaction_amount":    120.00,
        "max_transaction_amount":    200.00,
        "transaction_count_90d":     120,
        "transaction_count_30d":     40,
        "transaction_count_24h":     2,
        "known_merchants":           ["starbucks", "amazon", "netflix", "whole foods"],
        "known_countries":           ["US"],
        "known_devices":             ["dev_iphone_abc", "dev_macbook_xyz"],
        "known_merchant_categories": ["FOOD_BEVERAGE", "GROCERY", "SUBSCRIPTION"],
        "typical_hours":             list(range(7, 23)),
        "typical_days":              [0, 1, 2, 3, 4],
        "avg_daily_spend":           80.00,
        "spend_today":               30.00,
        "spend_this_week":           200.00,
        "last_transaction_at":       "2024-06-14T18:00:00Z",
        "high_risk_flags":           0,
    }


# ── Amount velocity ───────────────────────────────────────────────────────────

class TestAmountVelocity:
    def test_normal_amount_no_trigger(self):
        tx = make_tx(amount=50.00)
        r = signal_amount_velocity(tx, normal_baseline())
        assert not r.triggered

    def test_3x_triggers_low(self):
        tx = make_tx(amount=135.00)   # 3× avg
        r = signal_amount_velocity(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "low"

    def test_5x_triggers_medium(self):
        tx = make_tx(amount=225.00)   # 5× avg
        r = signal_amount_velocity(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "medium"

    def test_10x_triggers_high(self):
        tx = make_tx(amount=450.00)   # 10× avg
        r = signal_amount_velocity(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "high"

    def test_no_baseline_no_trigger(self):
        r = signal_amount_velocity(make_tx(), {})
        assert not r.triggered


# ── Geo mismatch ──────────────────────────────────────────────────────────────

class TestGeoMismatch:
    def test_matching_countries_no_trigger(self):
        tx = make_tx(
            device=DeviceInfo(geo_country="US"),
            card=CardInfo(card_country="US"),
        )
        r = signal_geo_mismatch(tx, normal_baseline())
        assert not r.triggered

    def test_mismatched_countries_triggers(self):
        tx = make_tx(
            device=DeviceInfo(geo_country="DE"),
            card=CardInfo(card_country="US"),
        )
        r = signal_geo_mismatch(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "high"
        assert "DE" in r.detail
        assert "US" in r.detail

    def test_no_device_no_trigger(self):
        tx = make_tx(card=CardInfo(card_country="US"))
        r = signal_geo_mismatch(tx, normal_baseline())
        assert not r.triggered


# ── High risk category ────────────────────────────────────────────────────────

class TestHighRiskCategory:
    def test_crypto_triggers_high(self):
        tx = make_tx(merchant=Merchant(name="Coinbase", category="CRYPTO"))
        r = signal_high_risk_category(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "high"

    def test_ach_triggers_medium(self):
        tx = make_tx(merchant=Merchant(name="Bank", category="ACH_TRANSFER"))
        r = signal_high_risk_category(tx, normal_baseline())
        assert r.triggered
        assert r.severity == "medium"

    def test_grocery_no_trigger(self):
        tx = make_tx(merchant=Merchant(name="Whole Foods", category="GROCERY"))
        r = signal_high_risk_category(tx, normal_baseline())
        assert not r.triggered


# ── New merchant ──────────────────────────────────────────────────────────────

class TestNewMerchant:
    def test_known_merchant_no_trigger(self):
        r = signal_new_merchant(make_tx(), normal_baseline())
        assert not r.triggered   # Starbucks is in known_merchants

    def test_new_merchant_triggers(self):
        tx = make_tx(merchant=Merchant(name="Suspicious Store", category="RETAIL"))
        r = signal_new_merchant(tx, normal_baseline())
        assert r.triggered

    def test_empty_baseline_no_trigger(self):
        r = signal_new_merchant(make_tx(), {})
        assert not r.triggered


# ── VPN/Tor ───────────────────────────────────────────────────────────────────

class TestVpnTor:
    def test_clean_device_no_trigger(self):
        tx = make_tx(device=DeviceInfo(is_vpn=False, is_tor=False, is_proxy=False))
        r = signal_vpn_tor(tx, normal_baseline())
        assert not r.triggered

    def test_vpn_triggers(self):
        tx = make_tx(device=DeviceInfo(is_vpn=True))
        r = signal_vpn_tor(tx, normal_baseline())
        assert r.triggered
        assert "VPN" in r.detail

    def test_tor_triggers(self):
        tx = make_tx(device=DeviceInfo(is_tor=True))
        r = signal_vpn_tor(tx, normal_baseline())
        assert r.triggered
        assert "Tor" in r.detail


# ── Rapid succession ──────────────────────────────────────────────────────────

class TestRapidSuccession:
    def test_normal_rate_no_trigger(self):
        r = signal_rapid_succession(make_tx(), normal_baseline())
        assert not r.triggered   # 2 tx in 24h vs avg 1.3/day

    def test_card_testing_pattern_triggers(self):
        baseline = {**normal_baseline(), "transaction_count_24h": 30, "transaction_count_30d": 60}
        r = signal_rapid_succession(make_tx(), baseline)
        assert r.triggered
        assert r.severity == "high"


# ── New user ──────────────────────────────────────────────────────────────────

class TestNewUser:
    def test_established_user_no_trigger(self):
        r = signal_new_user(make_tx(), normal_baseline())
        assert not r.triggered

    def test_brand_new_user_triggers(self):
        baseline = {**normal_baseline(), "transaction_count_90d": 1}
        r = signal_new_user(make_tx(), baseline)
        assert r.triggered


# ── Prior high risk ───────────────────────────────────────────────────────────

class TestPriorHighRisk:
    def test_clean_history_no_trigger(self):
        r = signal_prior_high_risk(make_tx(), normal_baseline())
        assert not r.triggered

    def test_one_flag_triggers_low(self):
        baseline = {**normal_baseline(), "high_risk_flags": 1}
        r = signal_prior_high_risk(make_tx(), baseline)
        assert r.triggered
        assert r.severity == "low"

    def test_three_flags_triggers_high(self):
        baseline = {**normal_baseline(), "high_risk_flags": 3}
        r = signal_prior_high_risk(make_tx(), baseline)
        assert r.triggered
        assert r.severity == "high"


# ── Composite scoring ─────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_clean_transaction_low_score(self):
        tx      = make_tx()
        results = run_all_signals(tx, normal_baseline())
        score, conf = compute_composite_score(results)
        assert score < 0.35, f"Expected low risk, got {score}"
        assert conf > 0.8

    def test_high_risk_transaction_high_score(self):
        """Multiple bad signals → DECLINE threshold."""
        tx = make_tx(
            amount   = 5000.00,   # 100× avg
            merchant = Merchant(name="Unknown Crypto", category="CRYPTO"),
            device   = DeviceInfo(geo_country="RU", is_vpn=True),
            card     = CardInfo(card_country="US"),
        )
        baseline = {**normal_baseline(), "high_risk_flags": 2, "transaction_count_24h": 15}
        results  = run_all_signals(tx, baseline)
        score, _ = compute_composite_score(results)
        assert score > 0.70, f"Expected high risk, got {score}"

    def test_no_signals_returns_low_baseline(self):
        from app.signals.engine import SignalResult
        no_signals = [
            SignalResult("s1", "S1", False, 0.0),
            SignalResult("s2", "S2", False, 0.0),
        ]
        score, conf = compute_composite_score(no_signals)
        assert score == 0.05
        assert conf  == 0.95

    def test_score_always_in_bounds(self):
        """Stress test: score must always be in [0, 1]."""
        from app.signals.engine import SignalResult
        for delta in [0, 0.1, 0.5, 1.0, 2.0, 5.0]:
            results = [SignalResult("s", "S", True, delta)]
            score, _ = compute_composite_score(results)
            assert 0.0 <= score <= 1.0, f"Score out of bounds for delta={delta}: {score}"
