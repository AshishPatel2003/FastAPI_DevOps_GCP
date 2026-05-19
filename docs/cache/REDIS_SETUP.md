# Redis Cloud Setup

1. Sign up for the free tier at Redis.com
2. Create a Database.
3. Obtain the connection string `rediss://...`
4. Set it as `REDIS_URL` in your GitHub Environment Secrets.

## Usage
- **WebSockets**: The `app.services.redis_service.RedisPubSubManager` uses Redis to broadcast WebSocket messages across instances.
- **Auth**: The `TokenBlacklist` stores logged out tokens to prevent reuse.
