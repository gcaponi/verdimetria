"""Run one or all Finestra C provider smokes without printing secrets."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from backend.config import provider_smoke

PROVIDERS = {
    "health": "smoke_health",
    "cdse": "smoke_cdse",
    "deepseek": "smoke_deepseek",
    "brevo": "smoke_brevo",
    "stripe": "smoke_stripe",
}


class Command(BaseCommand):
    help = "Smoke health/ready and one production provider integration"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("provider", choices=tuple(PROVIDERS))

    def handle(self, *args: Any, **options: Any) -> None:
        name = str(options["provider"])
        try:
            result = getattr(provider_smoke, PROVIDERS[name])()
        except Exception as error:
            raise CommandError(f"smoke {name} failed: {error}") from error
        summary = ", ".join(f"{key}={value}" for key, value in result.items())
        self.stdout.write(self.style.SUCCESS(f"smoke {name} ok ({summary})"))
