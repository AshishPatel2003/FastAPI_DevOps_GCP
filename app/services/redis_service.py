"""
Redis Service — Connection Pool + Pub/Sub Manager.

Architecture:
- A single async Redis connection pool is created at app startup (lifespan).
- The RedisManager class wraps pub/sub operations for WebSocket rooms.
- Token blacklisting uses standard SET with TTL for O(1) lookups.

Redis Cloud connection:
- Uses TLS (rediss://) automatically when the URL scheme is rediss://
- Connection pool is shared across all request handlers
"""

import contextlib
from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level pool — set during app startup via init_redis()
_redis_pool: Redis | None = None


# =============================================================================
# Connection Pool Management (called from main.py lifespan)
# =============================================================================

async def init_redis() -> Redis:
    """
    Initialize the Redis connection pool.

    Call once at application startup.
    Uses a connection pool with max_connections from settings.

    Returns:
        Connected Redis client instance.
    """
    global _redis_pool

    pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,          # Return str instead of bytes
        socket_timeout=5,               # 5 second operation timeout
        socket_connect_timeout=5,       # 5 second connection timeout
        health_check_interval=30,       # Ping Redis every 30s to detect stale connections
    )
    _redis_pool = Redis(connection_pool=pool)

    # Verify connectivity
    await _redis_pool.ping()
    logger.info(
        "Redis connection pool initialized",
        extra={"redis_url": settings.REDIS_URL.split("@")[-1]},  # Mask credentials
    )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool gracefully. Call at app shutdown."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis connection pool closed")


def get_redis() -> Redis:
    """
    Get the Redis client from the connection pool.

    Raises:
        RuntimeError: If Redis has not been initialized (init_redis not called).
    """
    if _redis_pool is None:
        raise RuntimeError("Redis pool not initialized. Call init_redis() at startup.")
    return _redis_pool


# =============================================================================
# Token Blacklist (for JWT logout)
# =============================================================================

class TokenBlacklist:
    """
    Redis-backed JWT token blacklist.

    On logout, the token's JTI (or full token string) is stored in Redis
    with a TTL matching the token's remaining lifetime. This prevents
    reuse of tokens after logout without needing DB queries.
    """

    PREFIX = "blacklist:token:"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def add(self, token: str, expire_seconds: int) -> None:
        """Add a token to the blacklist with automatic expiry."""
        key = f"{self.PREFIX}{token}"
        await self._redis.setex(key, expire_seconds, "1")
        logger.debug("Token blacklisted", extra={"expires_in": expire_seconds})

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token has been blacklisted."""
        key = f"{self.PREFIX}{token}"
        return bool(await self._redis.exists(key))


# =============================================================================
# Pub/Sub Manager (for WebSocket rooms)
# =============================================================================

class RedisPubSubManager:
    """
    Manages Redis Pub/Sub channels for WebSocket room broadcasting.

    Each WebSocket room maps to one Redis channel.
    When a client sends a message:
      1. The message is published to the Redis channel.
      2. All subscribers (other server instances or same-server connections)
         receive the message via their channel subscription.
      3. Each subscriber broadcasts to their connected WebSocket clients.

    This enables horizontal scaling — multiple Cloud Run instances can
    serve different WebSocket clients in the same room.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, channel: str, message: str) -> None:
        """
        Publish a message to a Redis channel.

        Args:
            channel: The Redis channel name (e.g., "room:general").
            message: JSON or plain string message payload.
        """
        await self._redis.publish(channel, message)
        logger.debug("Message published", extra={"channel": channel})

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncGenerator[PubSub, None]:
        """
        Context manager that subscribes to a Redis channel.

        Usage:
            async with pubsub_manager.subscribe("room:general") as pubsub:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        await websocket.send_text(message["data"])

        Args:
            channel: The Redis channel to subscribe to.

        Yields:
            An active PubSub instance.
        """
        # Create a NEW connection for pub/sub — cannot share with regular commands
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to channel", extra={"channel": channel})

        try:
            yield pubsub
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            logger.debug("Unsubscribed from channel", extra={"channel": channel})
