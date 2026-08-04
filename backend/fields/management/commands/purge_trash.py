"""Purge definitivo del cestino dopo 30 giorni (Fase 2 — piano sicurezza).

- Elimina (hard) Field e Intervention con `deleted_at` oltre la retention.
- Il guard DB richiede il bypass esplicito: `SET LOCAL verdimetria.allow_purge='on'`
  nella transazione del job — l'utenza runtime ordinaria resta bloccata.
- Gli artefatti collegati (PDF report in REPORT_CACHE_DIR) vengono eliminati
  solo dopo il purge DB riuscito, con gestione esplicita degli errori parziali.
- Ogni esecuzione scrive un AuditEntry action=purge (append-only).

Esecuzione: `python manage.py purge_trash` (cron giornaliero su pcc).
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from backend.fields.models import AnalysisJob, AuditEntry, Field, Intervention

RETENTION_DAYS = 30


class Command(BaseCommand):
    help = "Elimina definitivamente i record cestinati da oltre 30 giorni"

    def handle(self, *args: Any, **options: Any) -> None:
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        fields = list(Field.all_objects.filter(deleted_at__lt=cutoff))
        interventions = list(Intervention.all_objects.filter(deleted_at__lt=cutoff))
        if not fields and not interventions:
            self.stdout.write("purge_trash: niente da eliminare")
            return

        field_pks = [field.pk for field in fields]
        job_ids = list(
            AnalysisJob.objects.filter(field_id__in=field_pks).values_list("pk", flat=True)
        )

        with transaction.atomic():
            with connection.cursor() as cursor:
                # Bypass del guard riservato al purge job (Fase 2).
                cursor.execute("SET LOCAL verdimetria.allow_purge = 'on'")
            Field.all_objects.filter(pk__in=field_pks).delete()
            Intervention.all_objects.filter(
                pk__in=[intervention.pk for intervention in interventions]
            ).delete()
            AuditEntry.objects.create(
                action=AuditEntry.Action.PURGE,
                entity_type="trash",
                entity_id="batch",
                actor=None,
                metadata={
                    "cutoff": cutoff.isoformat(),
                    "fields": len(fields),
                    "interventions": len(interventions),
                    "job_pdfs": len(job_ids),
                },
            )

        # Artefatti collegati: eliminati solo dopo il purge DB riuscito;
        # un errore su un singolo file non blocca gli altri.
        pdf_errors = 0
        cache_dir = Path(settings.REPORT_CACHE_DIR)
        for job_id in job_ids:
            for pdf in cache_dir.glob(f"{job_id}-*.pdf"):
                try:
                    pdf.unlink()
                except OSError:
                    pdf_errors += 1

        self.stdout.write(
            f"purge_trash: {len(fields)} campi, {len(interventions)} interventi, "
            f"{len(job_ids)} job (PDF errori: {pdf_errors})"
        )
