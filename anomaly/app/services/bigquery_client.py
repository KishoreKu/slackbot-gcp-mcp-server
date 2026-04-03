"""
BigQueryClient — streams every scored transaction to BigQuery.

Table schema: anomaly_logs.transactions
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from google.cloud import bigquery

from app.models.transaction import ScoringResponse, TransactionRequest

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "slb-ai-agent-prod")
DATASET = os.environ.get("BQ_DATASET", "anomaly_logs")
TABLE = os.environ.get("BQ_TABLE", "transactions")
TABLE_ID = f"{PROJECT_ID}.{DATASET}.{TABLE}"

SCHEMA = [
    bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("amount", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("currency", "STRING"),
    bigquery.SchemaField("merchant_name", "STRING"),
    bigquery.SchemaField("merchant_category", "STRING"),
    bigquery.SchemaField("transaction_type", "STRING"),
    bigquery.SchemaField("risk_score", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("confidence", "FLOAT64"),
    bigquery.SchemaField("decision", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("explanation", "STRING"),
    bigquery.SchemaField("signals_json", "JSON"),
    bigquery.SchemaField("latency_ms", "FLOAT64"),
    bigquery.SchemaField("model_version", "STRING"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("confirmed_fraud", "BOOL"),
    bigquery.SchemaField("feedback_at", "TIMESTAMP"),
    bigquery.SchemaField("feedback_by", "STRING"),
]


class BigQueryClient:
    def __init__(self):
        self._client = bigquery.Client(project=PROJECT_ID)
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET}")
            dataset_ref.location = "US"
            self._client.create_dataset(dataset_ref, exists_ok=True)

            table_ref = bigquery.Table(TABLE_ID, schema=SCHEMA)
            table_ref.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="created_at",
            )
            self._client.create_table(table_ref, exists_ok=True)
            logger.info("BigQuery table ready: %s", TABLE_ID)
        except Exception as e:
            logger.warning("BigQuery table setup warning (non-fatal): %s", e)

    async def log_transaction(
        self,
        tx: TransactionRequest,
        result: ScoringResponse,
    ) -> None:
        row = {
            "transaction_id": tx.transaction_id,
            "user_id": tx.user_id,
            "amount": tx.amount,
            "currency": tx.currency,
            "merchant_name": tx.merchant.name,
            "merchant_category": tx.merchant.category,
            "transaction_type": tx.transaction_type.value,
            "risk_score": result.risk_score,
            "confidence": result.confidence,
            "decision": result.decision.value,
            "explanation": result.explanation,
            "signals_json": json.dumps([s.model_dump() for s in result.signals]),
            "latency_ms": result.latency_ms,
            "model_version": result.model_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "confirmed_fraud": None,
            "feedback_at": None,
            "feedback_by": None,
        }

        errors = self._client.insert_rows_json(TABLE_ID, [row])
        if errors:
            logger.warning("BigQuery insert errors: %s", errors)
        else:
            logger.debug("BigQuery row logged for tx=%s", tx.transaction_id)
