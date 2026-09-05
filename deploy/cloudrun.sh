#!/usr/bin/env bash
set -euo pipefail
: "${GCP_PROJECT:?Set GCP_PROJECT}"
REGION="${GCP_REGION:-asia-south1}"
SERVICE="${SERVICE_NAME:-arjuna-ai}"
REPO="${AR_REPOSITORY:-arjuna-ai}"
IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT}/${REPO}/${SERVICE}:$(date +%Y%m%d-%H%M%S)"

gcloud artifacts repositories describe "$REPO" --project "$GCP_PROJECT" --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --project "$GCP_PROJECT" --location "$REGION" --repository-format docker

gcloud builds submit --project "$GCP_PROJECT" --tag "$IMAGE" .
gcloud run deploy "$SERVICE" --project "$GCP_PROJECT" --region "$REGION" --image "$IMAGE" --platform managed --allow-unauthenticated --port 8080

echo "ARJUNA AI deployed. Configure production secrets, DATABASE_URL, custom domain and monitoring before opening the console to users."
