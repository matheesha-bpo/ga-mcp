#!/usr/bin/env bash
# Deploys the Google Analytics MCP gateway to Cloud Run.
# Safe to run again: every step skips what already exists.
#
# Usage:
#   PROJECT_ID=my-project ./scripts/deploy.sh
#
# Optional: REGION (default asia-south1), SERVICE (default ga-mcp),
#           SA_NAME (default ga-mcp), SECRET_NAME (default ga-mcp-secret)
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to your Google Cloud project id}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-ga-mcp}"
SA_NAME="${SA_NAME:-ga-mcp}"
SECRET_NAME="${SECRET_NAME:-ga-mcp-secret}"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

cd "$(dirname "$0")/.."

echo "==> Project ${PROJECT_ID}, region ${REGION}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Enabling APIs (takes a minute the first time)"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  analyticsdata.googleapis.com \
  analyticsadmin.googleapis.com

echo "==> Build permissions (new projects: Cloud Build uses the Compute default service account)"
gcloud services enable compute.googleapis.com
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/run.builder roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${BUILD_SA}" --role="${role}" --condition=None >/dev/null
done

echo "==> Service account ${SA_EMAIL}"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Google Analytics MCP (read-only)"
fi

echo "==> Shared secret ${SECRET_NAME}"
if ! gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  openssl rand -hex 32 | tr -d '\n' | gcloud secrets create "${SECRET_NAME}" \
    --replication-policy=automatic --data-file=-
  echo "    Created a new random secret."
fi
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "==> Deploying ${SERVICE} (Cloud Build builds the Dockerfile)"
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --service-account "${SA_EMAIL}" \
  --allow-unauthenticated \
  --set-secrets "MCP_SECRET=${SECRET_NAME}:latest" \
  --min-instances 0 \
  --max-instances 2 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 120 \
  --concurrency 20

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)')"

cat <<EOF

Done.

  Health check : ${URL}/healthz
  MCP endpoint : ${URL}/mcp?key=<MCP_SECRET>

Read the secret (keep it private):
  gcloud secrets versions access latest --secret=${SECRET_NAME}

Next: add ${SA_EMAIL} as a Viewer on your GA4 property
(GA4 Admin -> Property access management), then add the connector in Claude.
EOF
