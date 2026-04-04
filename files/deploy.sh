#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────
# Anomaly — GCP Deploy Script
# Usage: ./deploy.sh [PROJECT_ID] [REGION]
# ────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ID=${1:-"your-project-id"}
REGION=${2:-"us-central1"}
SERVICE_NAME="anomaly-api"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "→ Project:  ${PROJECT_ID}"
echo "→ Region:   ${REGION}"
echo "→ Service:  ${SERVICE_NAME}"
echo ""

# ── 1. Enable required APIs ────────────────────────────────
echo "[1/6] Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# ── 2. Create Firestore database (native mode) ─────────────
echo "[2/6] Setting up Firestore..."
gcloud firestore databases create \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --type=firestore-native 2>/dev/null || echo "  Firestore already exists, skipping."

# ── 3. Create Service Account ──────────────────────────────
echo "[3/6] Setting up service account..."
SA_NAME="anomaly-cloudrun-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Anomaly Cloud Run SA" \
  --project="${PROJECT_ID}" 2>/dev/null || echo "  SA already exists."

for ROLE in \
  "roles/datastore.user" \
  "roles/bigquery.dataEditor" \
  "roles/bigquery.jobUser" \
  "roles/secretmanager.secretAccessor" \
  "roles/aiplatform.user"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" --quiet
done

# ── 4. Build & push image ──────────────────────────────────
echo "[4/6] Building and pushing Docker image..."
gcloud builds submit \
  --tag="${IMAGE}:latest" \
  --project="${PROJECT_ID}" .

# ── 5. Deploy to Cloud Run ─────────────────────────────────
echo "[5/6] Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}:latest" \
  --platform=managed \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=80 \
  --timeout=30s \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION}" \
  --no-allow-unauthenticated \
  --project="${PROJECT_ID}"

echo "[6/6] Done!"
URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")
echo ""
echo "✓ Service URL: ${URL}"
echo ""
echo "Test it:"
echo "  curl -X POST ${URL}/v1/analyze \\"
echo "    -H 'Authorization: Bearer your-api-key' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d @tests/sample_transaction.json"
