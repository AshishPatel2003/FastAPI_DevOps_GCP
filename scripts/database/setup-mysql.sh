#!/usr/bin/env bash

# =========================================================================================
# Cloud SQL MySQL Provisioning Script (Reference)
# =========================================================================================

set -euo pipefail

BLUE='\033[0;34m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Cloud SQL MySQL Provisioner                                ${NC}"
echo -e "${BLUE}==============================================================${NC}"

read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
read -p "Enter preferred GCP region [default: asia-south1]: " GCP_REGION
GCP_REGION=${GCP_REGION:-asia-south1}
read -p "Enter Environment (dev/stage/prod) [default: dev]: " ENV
ENV=${ENV:-dev}

INSTANCE_NAME="fastapi-mysql-${ENV}"
DB_NAME="fastapi_db"
DB_USER="fastapi_user"
DB_PASSWORD=$(openssl rand -base64 15)

echo -e "\n${YELLOW}Provisioning Cloud SQL MySQL Instance: $INSTANCE_NAME...${NC}"
gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=MYSQL_8_0 \
    --cpu=1 \
    --memory=3840MB \
    --region="$GCP_REGION" \
    --project="$GCP_PROJECT_ID" \
    --quiet

gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME" --project="$GCP_PROJECT_ID" --quiet
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASSWORD" --project="$GCP_PROJECT_ID" --quiet

CONNECTION_NAME="$GCP_PROJECT_ID:$GCP_REGION:$INSTANCE_NAME"

echo -e "\n${GREEN}MySQL Provisioned Successfully!${NC}"
echo -e "CLOUD_SQL_INSTANCE: $CONNECTION_NAME"
echo -e "DATABASE_URL: mysql+aiomysql://$DB_USER:$DB_PASSWORD@localhost:3306/$DB_NAME"
