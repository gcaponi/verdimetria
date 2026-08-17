"""Alert operativi: catalogo chiuso, destinatario validato e errori sanificati."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from backend.fields.management.commands.send_ops_alert import EVENTS


@pytest.mark.parametrize("event", EVENTS)
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Verdimetria <ops@example.com>",
    OPS_ALERT_EMAIL="owner@example.com",
)
def test_each_allowlisted_event_sends_one_fixed_message(
    event: str, mailoutbox: list
) -> None:
    stdout = StringIO()

    call_command("send_ops_alert", event, stdout=stdout)

    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == ["owner@example.com"]
    assert (message.subject, message.body) == EVENTS[event]
    assert event in stdout.getvalue()


@pytest.mark.parametrize("recipient", ["", "not-an-email"])
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_recipient_is_required_and_validated(
    settings: object, recipient: str, mailoutbox: list
) -> None:
    settings.OPS_ALERT_EMAIL = recipient

    with pytest.raises(CommandError, match="OPS_ALERT_EMAIL"):
        call_command("send_ops_alert", "test")

    assert not mailoutbox


@override_settings(
    OPS_ALERT_EMAIL="owner@example.com",
    DEFAULT_FROM_EMAIL="Verdimetria <ops@example.com>",
)
def test_email_backend_error_is_sanitized() -> None:
    with (
        patch(
            "backend.fields.management.commands.send_ops_alert.send_mail",
            side_effect=RuntimeError("smtp password leaked"),
        ),
        pytest.raises(CommandError, match="Invio alert operativo fallito") as caught,
    ):
        call_command("send_ops_alert", "backup-failed")

    assert "password" not in str(caught.value)


@override_settings(OPS_ALERT_EMAIL="owner@example.com")
def test_unconfirmed_delivery_is_an_error() -> None:
    with (
        patch(
            "backend.fields.management.commands.send_ops_alert.send_mail",
            return_value=0,
        ),
        pytest.raises(CommandError, match="non confermato"),
    ):
        call_command("send_ops_alert", "test")
