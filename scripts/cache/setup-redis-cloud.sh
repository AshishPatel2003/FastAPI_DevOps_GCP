#!/usr/bin/env bash

# =========================================================================================
# Redis Cloud Setup Helper
# =========================================================================================

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   Redis Cloud Setup Helper                                   ${NC}"
echo -e "${BLUE}==============================================================${NC}"

echo -e "\n${YELLOW}Redis Cloud offers a generous 30MB Free Tier perfect for our WebSocket Pub/Sub and Token Blacklist.${NC}"
echo -e "This process cannot be fully automated. Please follow these steps:"
echo -e "1. Go to https://redis.com/try-free/"
echo -e "2. Create an account and a new 'Redis Stack' database."
echo -e "3. Under 'Security', copy the Public Endpoint and Password."
echo -e "4. Format your REDIS_URL like this: redis://default:YOUR_PASSWORD@YOUR_ENDPOINT:YOUR_PORT"

read -p "\nPaste your full REDIS_URL here to validate connectivity: " REDIS_URL

if [ -z "$REDIS_URL" ]; then
    echo "No URL provided. Exiting."
    exit 0
fi

echo -e "\nTesting connectivity via Python..."
python3 -c "
import asyncio
from redis.asyncio import Redis

async def test():
    try:
        r = Redis.from_url('$REDIS_URL')
        await r.ping()
        print('\n\033[0;32m✓ Successfully connected to Redis Cloud!\033[0m')
    except Exception as e:
        print(f'\n\033[0;31m✗ Connection failed: {e}\033[0m')
        
asyncio.run(test())
"

echo -e "\nAdd this to your GitHub Environment Secrets:"
echo -e "REDIS_URL: $REDIS_URL"
