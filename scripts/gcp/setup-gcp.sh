#!/usr/bin/env bash

# =========================================================================================
# Enterprise GCP Cloud Run & Workload Identity Federation (OIDC) Setup Script
# =========================================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Enterprise GCP Cloud Run Setup & OIDC Provisioner          ${NC}"
echo -e "${BLUE}==============================================================${NC}"

# 1. Validation & Inputs
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: 'gcloud' CLI is not installed.${NC}"
    exit 1
fi

read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
read -p "Enter your GitHub Repo in 'owner/repo' format (e.g. Octocat/Hello-World): " GITHUB_REPO
read -p "Enter preferred GCP region [default: asia-south1]: " GCP_REGION
GCP_REGION=${GCP_REGION:-asia-south1}

gcloud config set project "$GCP_PROJECT_ID" --quiet
GCP_PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT_ID" --format="value(projectNumber)")

# 2. Enable APIs
echo -e "\n${YELLOW}Step 1: Enabling Google Cloud APIs...${NC}"
gcloud services enable \
    artifactregistry.googleapis.com \
    run.googleapis.com \
    iam.googleapis.com \
    iamcredentials.googleapis.com \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    secretmanager.googleapis.com \
    --quiet
echo -e "${GREEN}✓ APIs enabled!${NC}"

# 3. Create Artifact Registry
echo -e "\n${YELLOW}Step 2: Provisioning Artifact Registry Docker Repository...${NC}"
if ! gcloud artifacts repositories describe fastapi-app --location="$GCP_REGION" &>/dev/null; then
    gcloud artifacts repositories create fastapi-app \
        --repository-format=docker \
        --location="$GCP_REGION" \
        --description="Docker repository for FastAPI deployments" \
        --quiet
fi
echo -e "${GREEN}✓ Artifact Registry 'fastapi-app' ready!${NC}"

# 4. Create Service Account
echo -e "\n${YELLOW}Step 3: Creating GitHub Deployer Service Account...${NC}"
DEPLOYER_SA_EMAIL="github-actions-deployer@$GCP_PROJECT_ID.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$DEPLOYER_SA_EMAIL" &>/dev/null; then
    gcloud iam service-accounts create github-actions-deployer \
        --display-name="GitHub Actions Deployer" \
        --quiet
fi

# 5. Bind Service Account IAM Roles
echo -e "\n${YELLOW}Step 4: Setting up IAM Role Bindings...${NC}"
ROLES=(
    "roles/run.admin"
    "roles/artifactregistry.writer"
    "roles/cloudsql.client"
    "roles/storage.admin"
    "roles/secretmanager.secretAccessor"
)
for role in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
        --member="serviceAccount:$DEPLOYER_SA_EMAIL" \
        --role="$role" \
        --quiet >/dev/null
done

DEFAULT_COMPUTE_SA="$GCP_PROJECT_NUMBER-compute@developer.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$DEFAULT_COMPUTE_SA" \
    --member="serviceAccount:$DEPLOYER_SA_EMAIL" \
    --role="roles/iam.serviceAccountUser" \
    --quiet >/dev/null

gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$DEFAULT_COMPUTE_SA" \
    --role="roles/run.invoker" \
    --quiet >/dev/null

# 6. Workload Identity Pool & Provider
echo -e "\n${YELLOW}Step 5: Provisioning Workload Identity Federation...${NC}"
POOL_NAME="github-actions-pool"
if ! gcloud iam workload-identity-pools describe "$POOL_NAME" --location="global" &>/dev/null; then
    gcloud iam workload-identity-pools create "$POOL_NAME" --location="global" --display-name="GitHub Actions Pool" --quiet
fi

PROVIDER_NAME="github-actions-provider"
OWNER_NAME=$(echo "$GITHUB_REPO" | cut -d'/' -f1)

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_NAME" --location="global" --workload-identity-pool="$POOL_NAME" &>/dev/null; then
    gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_NAME" \
        --location="global" \
        --workload-identity-pool="$POOL_NAME" \
        --display-name="GitHub Actions Provider" \
        --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
        --attribute-condition="assertion.repository.startsWith('$OWNER_NAME/')" \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --quiet
    echo -e "${GREEN}✓ Workload Identity Provider created to allow repos under '$OWNER_NAME/'!${NC}"
else
    echo -e "${BLUE}Workload Identity Provider '$PROVIDER_NAME' already exists. Ensuring attribute condition allows '$OWNER_NAME/'...${NC}"
    gcloud iam workload-identity-pools providers update-oidc "$PROVIDER_NAME" \
        --location="global" \
        --workload-identity-pool="$POOL_NAME" \
        --attribute-condition="assertion.repository.startsWith('$OWNER_NAME/')" \
        --quiet
    echo -e "${GREEN}✓ Workload Identity Provider updated!${NC}"
fi

gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA_EMAIL" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/$GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/$GITHUB_REPO" \
    --quiet >/dev/null

# 7. Create GCS Buckets (Public and Private for dev env as example)
echo -e "\n${YELLOW}Step 6: Provisioning Base GCS Buckets...${NC}"
PUBLIC_BUCKET="${GCP_PROJECT_ID}-public-dev"
PRIVATE_BUCKET="${GCP_PROJECT_ID}-private-dev"

if ! gcloud storage buckets describe "gs://$PUBLIC_BUCKET" &>/dev/null; then
    gcloud storage buckets create "gs://$PUBLIC_BUCKET" --location="$GCP_REGION" --uniform-bucket-level-access
    gcloud storage buckets add-iam-policy-binding "gs://$PUBLIC_BUCKET" --member="allUsers" --role="roles/storage.objectViewer"
    echo -e "${GREEN}✓ Public Bucket created: $PUBLIC_BUCKET${NC}"
fi

if ! gcloud storage buckets describe "gs://$PRIVATE_BUCKET" &>/dev/null; then
    gcloud storage buckets create "gs://$PRIVATE_BUCKET" --location="$GCP_REGION" --uniform-bucket-level-access
    echo -e "${GREEN}✓ Private Bucket created: $PRIVATE_BUCKET${NC}"
fi

# 8. Output
WIF_PROVIDER_URL="projects/$GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider"

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}   GCP RESOURCES SECURELY PROVISIONED!                        ${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "\n${YELLOW}[1] ENVIRONMENT SECRETS:${NC}"
echo -e "GCP_WORKLOAD_IDENTITY_PROVIDER: $WIF_PROVIDER_URL"
echo -e "GCP_SERVICE_ACCOUNT:            $DEPLOYER_SA_EMAIL"
echo -e "GCP_PROJECT_ID:                 $GCP_PROJECT_ID"
echo -e "JWT_SECRET_KEY:                 (generate a random 32+ char string)"
echo -e "DATABASE_URL:                   (run setup-cloudsql.sh to get this)"
echo -e "REDIS_URL:                      (run setup-redis-cloud.sh to get this)"

echo -e "\n${YELLOW}[2] ENVIRONMENT VARIABLES:${NC}"
echo -e "GCP_REGION:                     $GCP_REGION"
echo -e "GCP_ARTIFACT_REPO:              fastapi-app"
echo -e "GCS_PUBLIC_BUCKET:              $PUBLIC_BUCKET"
echo -e "GCS_PRIVATE_BUCKET:             $PRIVATE_BUCKET"
echo -e "CLOUD_SQL_INSTANCE:             (run setup-cloudsql.sh to get this)"
