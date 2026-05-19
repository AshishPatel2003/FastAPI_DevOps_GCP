#!/usr/bin/env bash

# =========================================================================================
# Local GCP Credentials Setup Script
# =========================================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Local GCP Credentials Key Generator                        ${NC}"
echo -e "${BLUE}==============================================================${NC}"

# Check gcloud CLI
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: 'gcloud' CLI is not installed.${NC}"
    exit 1
fi

# Prompt for Project ID
read -p "Enter your GCP Project ID: " GCP_PROJECT_ID
if [ -z "$GCP_PROJECT_ID" ]; then
    echo -e "${RED}Error: Project ID is required.${NC}"
    exit 1
fi

gcloud config set project "$GCP_PROJECT_ID" --quiet

# List existing service accounts so the user can see them
echo -e "\n${YELLOW}Retrieving service accounts for project: $GCP_PROJECT_ID...${NC}"
gcloud iam service-accounts list --project="$GCP_PROJECT_ID"

# Prompt for Service Account Email
DEFAULT_SA="github-actions-deployer@$GCP_PROJECT_ID.iam.gserviceaccount.com"
echo -e "\nEnter the Service Account email to generate key for."
read -p "[Default: $DEFAULT_SA]: " SA_EMAIL
SA_EMAIL=${SA_EMAIL:-$DEFAULT_SA}

KEY_FILE="gcp-key.json"
KEY_PATH="../../$KEY_FILE" # Save to project root

echo -e "\n${YELLOW}Generating private key for $SA_EMAIL...${NC}"

# Generate key
if gcloud iam service-accounts keys create "$KEY_PATH" \
    --iam-account="$SA_EMAIL" \
    --project="$GCP_PROJECT_ID" \
    --quiet; then
    
    echo -e "${GREEN}✓ Key file generated successfully at: $(realpath "$KEY_PATH")${NC}"
    
    # Auto-add key file to gitignore if not present
    GITIGNORE_PATH="../../.gitignore"
    if [ -f "$GITIGNORE_PATH" ]; then
        if ! grep -q "$KEY_FILE" "$GITIGNORE_PATH"; then
            echo -e "\n$KEY_FILE" >> "$GITIGNORE_PATH"
            echo -e "${GREEN}✓ Added $KEY_FILE to your .gitignore file.${NC}"
        fi
    fi

    # Output instructions
    echo -e "\n${GREEN}==============================================================${NC}"
    echo -e "${GREEN}   Setup Complete!                                            ${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    echo -e "\nTo use these credentials in your local environment, run:"
    echo -e "${YELLOW}export GOOGLE_APPLICATION_CREDENTIALS=\"\$(pwd)/$KEY_FILE\"${NC}"
    echo -e "\nOr add it to your local ${YELLOW}.env${NC} file (supported by our Settings loader):"
    echo -e "${YELLOW}GOOGLE_APPLICATION_CREDENTIALS=\"./$KEY_FILE\"${NC}"
else
    echo -e "${RED}Failed to generate key. Check if the Service Account exists and you have permission.${NC}"
fi
