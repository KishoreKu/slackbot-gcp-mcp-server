#!/bin/bash
# Backup n8n Cloud Run Configuration

SERVICE_NAME="westley-n8n-engine" 
PROJECT_ID="westley-technologies"
REGION="us-central1" 

echo "📦 Backing up Cloud Run service: $SERVICE_NAME from project: $PROJECT_ID..."

# Export the full YAML configuration
gcloud run services describe $SERVICE_NAME \
    --project $PROJECT_ID \
    --platform managed \
    --region $REGION \
    --format yaml > n8n/service-config.yaml

# Extract key environment variables for easy reference (excluding secrets)
gcloud run services describe $SERVICE_NAME \
    --project $PROJECT_ID \
    --platform managed \
    --region $REGION \
    --format="value(spec.template.spec.containers[0].env)" > n8n/env-vars-backup.txt

echo "✅ Backup complete! Files saved in n8n/ folder."
