"""Liveness/readiness probes are public, minimal and dependency bounded."""

from unittest.mock import MagicMock, patch

from django.test import Client

from backend.config import health as health_views


def test_health_is_dependency_free_and_not_cacheable() -> None:
    with (
        patch("backend.config.health._database_is_ready") as database_ready,
        patch("backend.config.health._redis_is_ready") as redis_ready,
    ):
        response = Client().get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["Cache-Control"] == "no-store"
    database_ready.assert_not_called()
    redis_ready.assert_not_called()


def test_ready_succeeds_only_when_database_and_redis_are_ready() -> None:
    with (
        patch("backend.config.health._database_is_ready", return_value=True),
        patch("backend.config.health._redis_is_ready", return_value=True),
    ):
        response = Client().get("/ready/")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["Cache-Control"] == "no-store"


def test_ready_fails_generically_and_short_circuits_when_database_is_down() -> None:
    with (
        patch("backend.config.health._database_is_ready", return_value=False),
        patch("backend.config.health._redis_is_ready") as redis_ready,
    ):
        response = Client().get("/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["Cache-Control"] == "no-store"
    redis_ready.assert_not_called()


def test_ready_fails_generically_when_redis_is_down() -> None:
    with (
        patch("backend.config.health._database_is_ready", return_value=True),
        patch("backend.config.health._redis_is_ready", return_value=False),
    ):
        response = Client().get("/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_database_probe_executes_select_one() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    with patch("backend.config.health.connection", connection):
        assert health_views._database_is_ready() is True

    cursor.execute.assert_called_once_with("SELECT 1")


def test_redis_probe_uses_short_timeouts_and_closes_client(settings: object) -> None:
    client = MagicMock()
    client.ping.return_value = True
    with patch("backend.config.health.redis.Redis.from_url", return_value=client) as from_url:
        assert health_views._redis_is_ready() is True

    from_url.assert_called_once_with(
        health_views.settings.CELERY_BROKER_URL,
        socket_connect_timeout=health_views.PROBE_TIMEOUT_SECONDS,
        socket_timeout=health_views.PROBE_TIMEOUT_SECONDS,
    )
    client.ping.assert_called_once_with()
    client.close.assert_called_once_with()


def test_probes_reject_non_get_methods() -> None:
    client = Client()

    assert client.post("/health/").status_code == 405
    assert client.post("/ready/").status_code == 405
