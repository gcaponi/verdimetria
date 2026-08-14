"""Provider smokes must call the shipped integrations, not a parallel path."""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from backend.config import provider_smoke
from src.ingestion.catalog_api import CatalogItem

FIELD_POLYGON = provider_smoke.SMOKE_POLYGON


def _catalog_item() -> CatalogItem:
    return CatalogItem(
        item_id="S2-smoke-1",
        acquired_at="2026-07-10T10:00:00Z",
        cloud_cover=4.5,
        collection="sentinel-2-l2a",
        geometry=FIELD_POLYGON,
    )


def test_smoke_health_hits_public_probe_urls() -> None:
    with patch(
        "backend.config.provider_smoke._get_json",
        side_effect=[{"status": "ok"}, {"status": "ready"}],
    ) as get_json:
        result = provider_smoke.smoke_health()

    assert result == {"health": {"status": "ok"}, "ready": {"status": "ready"}}
    assert get_json.call_args_list[0].args[0] == provider_smoke.DEFAULT_PROBE_URLS["health"]
    assert get_json.call_args_list[1].args[0] == provider_smoke.DEFAULT_PROBE_URLS["ready"]


def test_smoke_cdse_uses_oauth_session_and_catalog() -> None:
    session = object()
    with (
        patch("backend.config.provider_smoke.get_oauth_session", return_value=session) as oauth,
        patch(
            "backend.config.provider_smoke.fetch_catalog_items",
            return_value=[_catalog_item()],
        ) as fetch,
    ):
        result = provider_smoke.smoke_cdse()

    oauth.assert_called_once_with()
    fetch.assert_called_once()
    assert fetch.call_args.kwargs["oauth"] is session
    assert fetch.call_args.kwargs["max_items"] == 3
    assert result["scenes"] == 1
    assert result["latest"] == "S2-smoke-1"


def test_smoke_cdse_fails_when_catalog_is_empty() -> None:
    with (
        patch("backend.config.provider_smoke.get_oauth_session", return_value=object()),
        patch("backend.config.provider_smoke.fetch_catalog_items", return_value=[]),
    ):
        with pytest.raises(RuntimeError, match="no scenes"):
            provider_smoke.smoke_cdse()


def test_smoke_deepseek_requires_generated_insights() -> None:
    usage = {"model": "deepseek-v4-pro", "tokens_in": 10, "tokens_out": 20}
    block = {"status": "generated", "summary": "ok", "insights": [{}, {}]}
    with patch(
        "backend.config.provider_smoke.generate_insights",
        return_value=(block, usage),
    ) as generate:
        result = provider_smoke.smoke_deepseek()

    generate.assert_called_once_with(provider_smoke.SMOKE_METRICS)
    assert result["status"] == "generated"
    assert result["model"] == "deepseek-v4-pro"
    assert result["insights"] == 2


def test_smoke_deepseek_rejects_rule_based_fallback() -> None:
    with patch(
        "backend.config.provider_smoke.generate_insights",
        return_value=({"status": "fallback", "insights": []}, None),
    ):
        with pytest.raises(RuntimeError, match="fell back"):
            provider_smoke.smoke_deepseek()


def test_smoke_brevo_runs_send_ops_alert_command() -> None:
    with patch("backend.config.provider_smoke.call_command") as command:
        result = provider_smoke.smoke_brevo()

    command.assert_called_once_with("send_ops_alert", "test")
    assert result == {"event": "test", "accepted": True}


def test_smoke_stripe_retrieves_account_with_settings_key(settings: Any) -> None:
    settings.STRIPE_SECRET_KEY = "sk_test_smoke"
    account = MagicMock()
    account.id = "acct_smoke"
    with patch(
        "backend.config.provider_smoke.stripe.Account.retrieve",
        return_value=account,
    ) as retrieve:
        result = provider_smoke.smoke_stripe()

    retrieve.assert_called_once_with()
    assert result["account_id"] == "acct_smoke"


def test_smoke_stripe_fails_when_secret_missing(settings: Any) -> None:
    settings.STRIPE_SECRET_KEY = ""
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY is empty"):
        provider_smoke.smoke_stripe()


def test_management_command_runs_named_provider() -> None:
    stdout = StringIO()
    with patch(
        "backend.config.provider_smoke.smoke_cdse",
        return_value={"scenes": 2, "latest": "S2-x"},
    ) as smoke:
        call_command("smoke_providers", "cdse", stdout=stdout)

    smoke.assert_called_once_with()
    assert "smoke cdse ok" in stdout.getvalue()


def test_management_command_surfaces_provider_failure() -> None:
    with patch(
        "backend.config.provider_smoke.smoke_stripe",
        side_effect=RuntimeError("denied"),
    ):
        with pytest.raises(CommandError, match="smoke stripe failed"):
            call_command("smoke_providers", "stripe")
