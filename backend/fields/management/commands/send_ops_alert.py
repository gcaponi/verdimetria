"""Send one allowlisted operational alert through Django's email backend."""

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

EVENTS: dict[str, tuple[str, str]] = {
    "test": (
        "[Verdimetria][TEST] Alert operativi attivi",
        "Collaudo consegna completato. Non e' richiesto alcun intervento.",
    ),
    "backup-failed": (
        "[Verdimetria][CRITICO] Backup pgBackRest fallito",
        (
            "Un job full o differential non e' terminato correttamente. "
            "Verificare subito il journal del servizio pgBackRest e il runbook DR."
        ),
    ),
    "backup-stale": (
        "[Verdimetria][CRITICO] Backup troppo vecchio",
        (
            "Il marker dell'ultimo backup riuscito manca o supera 30 ore. "
            "Verificare timer, repository pgBackRest e spazio disponibile."
        ),
    ),
    "wal-stalled": (
        "[Verdimetria][CRITICO] Archiviazione WAL bloccata",
        (
            "La coda WAL contiene segmenti non archiviati da oltre 10 minuti "
            "oppure l'ultimo errore non risulta recuperato. "
            "Verificare PostgreSQL e pgBackRest."
        ),
    ),
    "disk-pressure": (
        "[Verdimetria][ALTO] Spazio disco o inode oltre soglia",
        (
            "Disco o inode usati hanno raggiunto almeno l'80%. "
            "Verificare database, repository backup e log prima dell'esaurimento."
        ),
    ),
    "mirror-stale": (
        "[Verdimetria][ALTO] Mirror off-VPS non aggiornato",
        (
            "L'heartbeat del mirror sul disco Back-Up manca o supera 8 ore. "
            "Verificare portatile, timer user, rete SSH e rsync."
        ),
    ),
}


class Command(BaseCommand):
    help = "Invia un alert operativo Verdimetria da un catalogo fisso"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("event", choices=tuple(EVENTS))

    def handle(self, *args: Any, **options: Any) -> None:
        recipient = settings.OPS_ALERT_EMAIL.strip()
        if not recipient:
            raise CommandError("OPS_ALERT_EMAIL non configurata")
        try:
            validate_email(recipient)
        except ValidationError as error:
            raise CommandError("OPS_ALERT_EMAIL non valida") from error

        event = str(options["event"])
        subject, body = EVENTS[event]
        try:
            delivered = send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
        except Exception as error:
            raise CommandError("Invio alert operativo fallito") from error
        if delivered != 1:
            raise CommandError("Invio alert operativo non confermato")

        self.stdout.write(self.style.SUCCESS(f"Alert operativo inviato: {event}"))
