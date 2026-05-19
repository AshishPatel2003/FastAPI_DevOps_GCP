"""
WebSocket Chat Router with Redis Pub/Sub integration.

This module provides a horizontal-scalable WebSocket chat endpoint.
It uses Redis Pub/Sub to broadcast messages across multiple server instances.
"""

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from redis.asyncio.client import PubSub

from app.core.logging import get_logger
from app.core.security import decode_token
from app.services.redis_service import RedisPubSubManager, get_redis

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> str | None:
    """
    Authenticate a WebSocket connection using a JWT token.

    Because WebSockets cannot send standard HTTP headers easily in browsers,
    the token is usually passed as a query parameter: ?token=...
    """
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return None

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token payload")
            return None
        return str(user_id)
    except JWTError:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return None


async def _pubsub_listener(pubsub: PubSub, websocket: WebSocket) -> None:
    """
    Listen for messages on the Redis Pub/Sub channel and send them to the WebSocket.

    This runs as a background task for each connected WebSocket.
    """
    try:
        async for message in pubsub.listen():
            # filter out subscribe/unsubscribe confirmation messages
            if message["type"] == "message":
                data = message["data"]
                # data is expected to be a string (JSON encoded message)
                await websocket.send_text(data)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Error reading from pubsub: {exc}")
    finally:
        logger.debug("Pub/sub listener task exiting")


@router.websocket("/{room_id}")
async def websocket_chat(
    websocket: WebSocket,
    room_id: str,
    token: str | None = Query(None),
) -> None:
    """
    WebSocket endpoint for a specific chat room.

    Expects JWT authentication via the `token` query parameter.
    Messages sent by the client are published to the Redis channel `room:{room_id}`.
    Messages published to that channel are received by this endpoint and sent to the client.
    """
    user_id = await _authenticate_ws(websocket, token)
    if not user_id:
        return

    await websocket.accept()
    logger.info(f"WebSocket client connected to room {room_id}", extra={"user_id": user_id})

    redis = get_redis()
    pubsub_manager = RedisPubSubManager(redis)
    channel_name = f"room:{room_id}"
    listener_task = None

    try:
        # Subscribe to the room's Redis channel
        async with pubsub_manager.subscribe(channel_name) as pubsub:
            # Start background task to listen for Redis messages and push to WS
            listener_task = asyncio.create_task(_pubsub_listener(pubsub, websocket))

            # Broadcast that a user joined
            join_msg = json.dumps({
                "type": "system",
                "user_id": user_id,
                "content": f"User {user_id} joined the room.",
            })
            await pubsub_manager.publish(channel_name, join_msg)

            # Main loop: receive messages from WS and publish to Redis
            while True:
                data = await websocket.receive_text()

                # Optional: parse JSON from client to validate format,
                # but here we just wrap it and broadcast.
                broadcast_msg = json.dumps({
                    "type": "chat",
                    "user_id": user_id,
                    "content": data,
                })
                await pubsub_manager.publish(channel_name, broadcast_msg)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from room {room_id}", extra={"user_id": user_id})
        leave_msg = json.dumps({
            "type": "system",
            "user_id": user_id,
            "content": f"User {user_id} left the room.",
        })
        # Note: We must use a new redis client/manager call here because the context
        # manager `async with pubsub_manager.subscribe(...)` might have already closed
        await pubsub_manager.publish(channel_name, leave_msg)

    except Exception as exc:  # noqa: BLE001
        logger.error(f"WebSocket error in room {room_id}: {exc}")
        if not websocket.client_state.name == "DISCONNECTED":
            await websocket.close(code=1011, reason="Internal server error")

    finally:
        # Ensure the listener task is cancelled when the connection drops
        if listener_task and not listener_task.done():
            listener_task.cancel()
