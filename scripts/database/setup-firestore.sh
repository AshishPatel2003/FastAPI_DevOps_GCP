#!/usr/bin/env bash

# =========================================================================================
# Firestore Setup Helper (Reference)
# =========================================================================================

set -euo pipefail

BLUE='\033[0;34m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Firestore Setup Helper                                     ${NC}"
echo -e "${BLUE}==============================================================${NC}"

read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
read -p "Enter preferred GCP region [default: asia-south1]: " GCP_REGION
GCP_REGION=${GCP_REGION:-asia-south1}

echo -e "\n${YELLOW}Enabling Firestore API...${NC}"
gcloud services enable firestore.googleapis.com --project="$GCP_PROJECT_ID" --quiet

echo -e "\n${YELLOW}Creating Firestore Native Database...${NC}"
if ! gcloud firestore databases describe --project="$GCP_PROJECT_ID" &>/dev/null; then
    gcloud firestore databases create --location="$GCP_REGION" --type=firestore-native --project="$GCP_PROJECT_ID" --quiet || true
    echo -e "${GREEN}✓ Firestore Native Database created.${NC}"
else
    echo -e "${BLUE}Firestore is already enabled for this project.${NC}"
fi

echo -e "\n${GREEN}Firestore Setup Complete!${NC}"
echo -e "In FastAPI, use the 'google-cloud-firestore' package."
echo -e "Cloud Run will authenticate automatically using the default compute service account."
