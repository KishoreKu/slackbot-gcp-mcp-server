"""
Anomaly — Transaction Scoring API
Westley Group
Cloud Run entrypoint
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.transaction import TransactionRequest, ScoringResponse
from app.services.scorer import ScoringService
from app.services.firestore_client import FirestoreClient
from app.services.bigquery_client import BigQueryClient
from app.services.gemini_client import GeminiClient
from app.middleware.auth import verify_api_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Shared service instances (initialised once at startup) ──────────────────
firestore: FirestoreClient = None
bigquery: BigQueryClient = None
gemini: GeminiClient = None
scorer: ScoringService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise GCP clients once on container start."""
    global firestore, bigquery, gemini, scorer
    logger.info("Initialising GCP clients...")
    firestore = FirestoreClient()
    bigquery  = BigQueryClient()
    gemini    = GeminiClient()
    scorer    = ScoringService(firestore, gemini)
    logger.info("All clients ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Anomaly API",
    description="Real-time transaction anomaly detection with plain-English explanations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "anomaly-api"}


# ── Main scoring endpoint ───────────────────────────────────────────────────
@app.post(
    "/v1/analyze",
    response_model=ScoringResponse,
    dependencies=[Depends(verify_api_key)],
)
async def analyze_transaction(
    request: Request,
    tx: TransactionRequest,
):
    start = time.monotonic()

    try:
        result = await scorer.score(tx)
    except Exception as e:
        logger.exception("Scoring failed for tx %s", tx.transaction_id)
        raise HTTPException(status_code=500, detail=str(e))

    latency_ms = round((time.monotonic() - start) * 1000, 1)
    result.latency_ms = latency_ms

    # ── Fire-and-forget audit log to BigQuery ──
    try:
        await bigquery.log_transaction(tx, result)
    except Exception:
        logger.warning("BigQuery log failed — non-fatal", exc_info=True)

    logger.info(
        "tx=%s user=%s score=%.2f decision=%s latency=%.1fms",
        tx.transaction_id,
        tx.user_id,
        result.risk_score,
        result.decision,
        latency_ms,
    )
    return result


# ── Baseline update webhook (called by scheduled Cloud Run Job) ─────────────
@app.post("/internal/baselines/refresh", include_in_schema=False)
async def refresh_baselines(request: Request):
    """Internal endpoint — no external auth, only reachable inside VPC."""
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    await firestore.refresh_baseline(user_id)
    return {"status": "ok", "user_id": user_id}
