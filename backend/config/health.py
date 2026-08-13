"""Minimal process liveness and dependency readiness probes."""

from contextlib import suppress
from typing import Any

import redis
from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

PROBE_TIMEOUT_SECONDS = 1.0


def _json_response(payload: dict[str, Any], *, status: int = 200) -> JsonResponse:
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _database_is_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except DatabaseError:
        return False


def _redis_is_ready() -> bool:
    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
            socket_timeout=PROBE_TIMEOUT_SECONDS,
        )
        return bool(client.ping())
    except (redis.RedisError, ValueError):
        return False
    finally:
        if client is not None:
            with suppress(redis.RedisError):
                client.close()


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Liveness: the Django process can serve requests; no dependency I/O."""
    return _json_response({"status": "ok"})


@require_GET
def ready(request: HttpRequest) -> JsonResponse:
    """Readiness: only infrastructure required to accept application work."""
    if _database_is_ready() and _redis_is_ready():
        return _json_response({"status": "ready"})
    return _json_response({"status": "unavailable"}, status=503)
