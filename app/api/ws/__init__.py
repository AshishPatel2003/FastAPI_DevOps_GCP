"""WebSocket package exports."""

from app.api.ws.chat import router as ws_router

__all__ = ["ws_router"]
