"""
FastAPI Middleware for Request/Response Logging.

Logs HTTP requests, their duration, and status codes.
Integrates with the GCP Cloud Logging structure defined in app.core.logging.
"""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import get_logger

logger = get_logger("app.middleware.logging")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs incoming requests and outgoing responses.

    Adds a unique request ID (trace ID) to each request and calculates processing time.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate a unique trace ID for this request
        # If GCP Load Balancer adds a trace header (X-Cloud-Trace-Context),
        # we could parse it here for distributed tracing.
        trace_id = request.headers.get("X-Cloud-Trace-Context", str(uuid.uuid4()))

        start_time = time.time()

        # Log request start (optional, usually logging response is enough)
        # logger.debug(
        #     f"Request started: {request.method} {request.url.path}",
        #     extra={"trace_id": trace_id, "method": request.method, "path": request.url.path}
        # )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log request completion with status code and duration
            logger.info(
                f"HTTP Request: {request.method} {request.url.path} - Status: {response.status_code} - {process_time:.3f}s",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_s": process_time,
                    "client_ip": request.client.host if request.client else None,
                },
            )
            return response

        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                f"HTTP Request Error: {request.method} {request.url.path} - {process_time:.3f}s",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_s": process_time,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise
