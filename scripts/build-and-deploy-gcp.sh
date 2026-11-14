#!/usr/bin/env bash
# Prerequisites: gcloud auth login, terraform, billing, HTTPS OIDC provider.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${GCP_PROJECT:?set GCP_PROJECT}"
: "${GCP_REGION:=us-central1}"
: "${OIDC_ISSUER:?set HTTPS OIDC_ISSUER}"
: "${TF_VAR_db_password:?set TF_VAR_db_password (unique, secret)}"
: "${VITE_OIDC_CLIENT_ID:=launchpilot-web}"
[[ "$OIDC_ISSUER" == https://* ]] || { echo "OIDC_ISSUER must use HTTPS" >&2; exit 1; }
for cmd in gcloud terraform; do command -v "$cmd" >/dev/null || { echo "$cmd not installed" >&2; exit 1; }; done
cd "$ROOT"
gcloud config set project "$GCP_PROJECT"
gcloud services enable artifactregistry.googleapis.com cloudbuild.googleapis.com run.googleapis.com
if ! gcloud artifacts repositories describe launchpilot --location="$GCP_REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create launchpilot --repository-format=docker --location="$GCP_REGION"
fi
IMAGE="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/launchpilot/api:v2"
gcloud builds submit --config=cloudbuild.yaml --substitutions="_IMAGE=$IMAGE,_OIDC_ISSUER=$OIDC_ISSUER,_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID" .
cd infra/terraform/gcp
terraform init
terraform apply -var="project_id=$GCP_PROJECT" -var="region=$GCP_REGION" -var="image_url=$IMAGE" -var="oidc_issuer=$OIDC_ISSUER"
gcloud run jobs execute launchpilot-migrate --region="$GCP_REGION" --wait
URL="$(terraform output -raw launchpilot_url)"
echo "Deployment URL: $URL"
echo "ACTION REQUIRED: register $URL/ as an allowed callback + logout URI for your OIDC SPA client."
echo "Next: verify login, role denial, /api/health, Cloud Monitoring, and SLO alerts."
echo "Cloud SQL, Redis, Cloud Run and related networking resources incur charges."
