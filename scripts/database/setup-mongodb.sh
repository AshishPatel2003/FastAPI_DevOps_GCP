#!/usr/bin/env bash

# =========================================================================================
# MongoDB Atlas Database Provisioning Helper (Reference)
# =========================================================================================

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   MongoDB Atlas Helper                                       ${NC}"
echo -e "${BLUE}==============================================================${NC}"

echo -e "\n${YELLOW}MongoDB Atlas offers a generous M0 Free Tier.${NC}"
echo -e "1. Go to https://www.mongodb.com/cloud/atlas/register"
echo -e "2. Create an M0 Free Cluster in your preferred region (e.g., AWS/GCP ap-south-1)."
echo -e "3. In Network Access, whitelist IP 0.0.0.0/0 (required for Cloud Run without static IP/NAT)."
echo -e "4. In Database Access, create a database user and copy the password."
echo -e "5. Click 'Connect' -> 'Connect your application' -> Driver: Python, Version: 3.11+"

read -p "\nPaste your MONGODB_URL here: " MONGODB_URL

if [ -z "$MONGODB_URL" ]; then
    echo "No URL provided. Exiting."
    exit 0
fi

echo -e "\nAdd this to your GitHub Environment Secrets:"
echo -e "DATABASE_URL: $MONGODB_URL"
echo -e "\n${BLUE}Note:${NC} In FastAPI, replace SQLAlchemy with Motor (async PyMongo) or Beanie (ODM)."
