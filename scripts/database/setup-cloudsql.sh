#!/usr/bin/env bash

# =========================================================================================
# Cloud SQL PostgreSQL Provisioning Script
# =========================================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Cloud SQL PostgreSQL Provisioner                           ${NC}"
echo -e "${BLUE}==============================================================${NC}"

read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
read -p "Enter preferred GCP region [default: asia-south1]: " GCP_REGION
GCP_REGION=${GCP_REGION:-asia-south1}
read -p "Enter Environment (dev/stage/prod) [default: dev]: " ENV
ENV=${ENV:-dev}

# Prompt for Instance Name
read -p "Enter Cloud SQL Instance Name [default: fastapi-db-${ENV}]: " INPUT_INSTANCE
INSTANCE_NAME=${INPUT_INSTANCE:-fastapi-db-${ENV}}

# Prompt for Database Version
read -p "Enter Database Version (e.g., POSTGRES_15, POSTGRES_16) [default: POSTGRES_15]: " DB_VERSION
DB_VERSION=${DB_VERSION:-POSTGRES_15}

# Prompt for Machine Specifications (CPU & Memory)
# Note: Custom instances typically require at least 3.75GB (3840MB) of memory per vCPU.
read -p "Enter vCPU count [default: 1]: " CPU_COUNT
CPU_COUNT=${CPU_COUNT:-1}

read -p "Enter Memory size (e.g., 3840MB, 4GB) [default: 3840MB]: " MEMORY_SIZE
MEMORY_SIZE=${MEMORY_SIZE:-3840MB}

# Prompt for Storage Specifications
read -p "Enter Storage capacity in GB (min 10) [default: 10]: " STORAGE_SIZE
STORAGE_SIZE=${STORAGE_SIZE:-10}

read -p "Enter Storage type (SSD or HDD) [default: SSD]: " STORAGE_TYPE
STORAGE_TYPE=${STORAGE_TYPE:-SSD}

read -p "Enable automatic storage resizing? (y/n) [default: y]: " AUTO_RESIZE_INPUT
AUTO_RESIZE_INPUT=${AUTO_RESIZE_INPUT:-y}
if [[ "$AUTO_RESIZE_INPUT" =~ ^[Yy]$ ]]; then
    AUTO_RESIZE_FLAG="--storage-auto-increase"
else
    AUTO_RESIZE_FLAG="--no-storage-auto-increase"
fi


# Prompt for Database Credentials
read -p "Enter Database Name [default: fastapi_db]: " INPUT_DB_NAME
DB_NAME=${INPUT_DB_NAME:-fastapi_db}

read -p "Enter Database User [default: fastapi_user]: " INPUT_DB_USER
DB_USER=${INPUT_DB_USER:-fastapi_user}

# Generate a random password if not provided
DEFAULT_PASSWORD=$(openssl rand -base64 15)
read -p "Enter Database Password [default: (auto-generated)]: " DB_PASSWORD
DB_PASSWORD=${DB_PASSWORD:-$DEFAULT_PASSWORD}

echo -e "\n${YELLOW}Provisioning Cloud SQL Instance: $INSTANCE_NAME...${NC}"
echo -e "Specs: $CPU_COUNT vCPU, $MEMORY_SIZE Memory, Engine: $DB_VERSION"
echo -e "Storage: $STORAGE_SIZE GB ($STORAGE_TYPE), Auto-resize: $AUTO_RESIZE_INPUT"
echo -e "Note: This will take 5-10 minutes."

if gcloud sql instances describe "$INSTANCE_NAME" --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo -e "${BLUE}Instance $INSTANCE_NAME already exists.${NC}"
else
    echo -e "\n${BLUE}Running command:${NC}"
    echo "gcloud sql instances create \"$INSTANCE_NAME\" \\"
    echo "    --database-version=\"$DB_VERSION\" \\"
    echo "    --cpu=\"$CPU_COUNT\" \\"
    echo "    --memory=\"$MEMORY_SIZE\" \\"
    echo "    --storage-size=\"$STORAGE_SIZE\" \\"
    echo "    --storage-type=\"$STORAGE_TYPE\" \\"
    echo "    $AUTO_RESIZE_FLAG \\"
    echo "    --edition=enterprise \\"
    echo "    --region=\"$GCP_REGION\" \\"
    echo "    --project=\"$GCP_PROJECT_ID\" \\"
    echo "    --quiet"
    echo ""

    gcloud sql instances create "$INSTANCE_NAME" \
        --database-version="$DB_VERSION" \
        --cpu="$CPU_COUNT" \
        --memory="$MEMORY_SIZE" \
        --storage-size="$STORAGE_SIZE" \
        --storage-type="$STORAGE_TYPE" \
        $AUTO_RESIZE_FLAG \
        --edition=enterprise \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --quiet
fi



echo -e "\n${YELLOW}Creating Database and User...${NC}"
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME" --project="$GCP_PROJECT_ID" --quiet || true
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASSWORD" --project="$GCP_PROJECT_ID" --quiet || gcloud sql users set-password "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASSWORD" --project="$GCP_PROJECT_ID" --quiet

CONNECTION_NAME="$GCP_PROJECT_ID:$GCP_REGION:$INSTANCE_NAME"

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}   Cloud SQL Provisioned Successfully!                        ${NC}"
echo -e "${GREEN}==============================================================${NC}"
echo -e "\nAdd these to your GitHub ${ENV} environment:"
echo -e "\n${YELLOW}ENVIRONMENT VARIABLES:${NC}"
echo -e "CLOUD_SQL_INSTANCE: $CONNECTION_NAME"
echo -e "\n${YELLOW}SECRETS:${NC}"
echo -e "DATABASE_URL: postgresql+asyncpg://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo -e "\n${BLUE}Note:${NC} Cloud Run will inject the unix socket at runtime. Your app is configured to handle this automatically when CLOUD_SQL_INSTANCE is set."

