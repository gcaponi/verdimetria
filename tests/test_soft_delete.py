"""Test Fase 2 — cestino (soft delete), purge 30 giorni, vincoli DB.

Il DB di test ha i trigger guard attivi (migration 0006): le operazioni
destructive senza bypass GUC devono fallire a livello database.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.models import (
    AnalysisJob,
    AuditEntry,
    BoundaryVersion,
    Field,
    Intervention,
)

FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.61, 36.92],
        [14.61, 36.93],
        [14.60, 36.93],
        [14.60, 36.92],
    ]],
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def field(api_client: APIClient, user: User) -> Field:
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo cestino", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert response.status_code == 201
    return Field.objects.get(pk=response.data["id"])


@pytest.mark.django_db
def test_delete_field_creates_tombstone(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)

    response = api_client.delete(f"/api/v1/fields/{field.pk}/")

    assert response.status_code == 204
    field.refresh_from_db()
    assert field.deleted_at is not None
    assert field.deleted_by == user
    # Il record esiste ancora nel DB (recuperabile), ma sparisce dalle viste.
    assert Field.all_objects.filter(pk=field.pk).exists()
    assert Field.objects.filter(pk=field.pk).count() == 0
    listing = api_client.get("/api/v1/fields/")
    assert listing.data == []
    audit = AuditEntry.objects.get(entity_type="field", entity_id=str(field.pk))
    assert audit.action == AuditEntry.Action.DELETE
    assert audit.actor == user


@pytest.mark.django_db
def test_trash_list_shows_deleted_fields(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")

    response = api_client.get("/api/v1/fields/trash/")

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["id"] == str(field.pk)
    assert response.data[0]["deleted_at"] is not None


@pytest.mark.django_db
def test_restore_field_brings_it_back(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")

    response = api_client.post(f"/api/v1/fields/{field.pk}/restore/", {}, format="json")

    assert response.status_code == 200
    field.refresh_from_db()
    assert field.deleted_at is None
    listing = api_client.get("/api/v1/fields/")
    assert len(listing.data) == 1
    assert AuditEntry.objects.filter(
        entity_type="field", entity_id=str(field.pk), action=AuditEntry.Action.RESTORE
    ).exists()


@pytest.mark.django_db
def test_restore_alive_field_is_conflict(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    response = api_client.post(f"/api/v1/fields/{field.pk}/restore/", {}, format="json")
    assert response.status_code == 409


@pytest.mark.django_db
def test_other_user_cannot_restore(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")

    other = User.objects.create_user(email="other@example.com", password="StrongPass-2026!")
    api_client.force_authenticate(other)
    response = api_client.post(f"/api/v1/fields/{field.pk}/restore/", {}, format="json")

    assert response.status_code == 404
    field.refresh_from_db()
    assert field.deleted_at is not None


@pytest.mark.django_db
def test_demo_field_cannot_be_trashed(api_client: APIClient, user: User, field: Field) -> None:
    field.is_demo = True
    field.save(update_fields=("is_demo",))
    api_client.force_authenticate(user)

    response = api_client.delete(f"/api/v1/fields/{field.pk}/")

    assert response.status_code == 409
    field.refresh_from_db()
    assert field.deleted_at is None


@pytest.mark.django_db
def test_delete_intervention_creates_tombstone(
    api_client: APIClient, user: User, field: Field
) -> None:
    api_client.force_authenticate(user)
    created = api_client.post(
        f"/api/v1/fields/{field.pk}/interventions/",
        {"kind": "irrigation", "date": "2026-08-01", "notes": "prova"},
        format="json",
    )
    assert created.status_code == 201
    intervention_id = created.data["id"]

    response = api_client.delete(f"/api/v1/interventions/{intervention_id}/")

    assert response.status_code == 204
    assert Intervention.objects.count() == 0
    assert Intervention.all_objects.filter(pk=intervention_id).exists()
    listing = api_client.get(f"/api/v1/fields/{field.pk}/interventions/")
    assert listing.data == []
    assert AuditEntry.objects.filter(
        entity_type="intervention", entity_id=intervention_id
    ).exists()


@pytest.mark.django_db
def test_jobs_of_trashed_field_are_hidden(api_client: APIClient, user: User, field: Field) -> None:
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=1,
        idempotency_key="job-cestino",
        params={},
        status=AnalysisJob.Status.COMPLETED,
        result={},
    )
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")

    listing = api_client.get("/api/v1/jobs/")
    assert all(item["id"] != str(job.pk) for item in listing.data)


@pytest.mark.django_db
def test_purge_removes_records_older_than_30_days(
    api_client: APIClient, user: User, field: Field
) -> None:
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")
    old = Field.all_objects.get(pk=field.pk)
    Field.all_objects.filter(pk=old.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )

    call_command("purge_trash", skip_backup_check=True)

    assert not Field.all_objects.filter(pk=field.pk).exists()
    purge_audit = AuditEntry.objects.get(action=AuditEntry.Action.PURGE)
    assert purge_audit.metadata["fields"] == 1


@pytest.mark.django_db
def test_purge_preserves_recent_trash(api_client: APIClient, user: User, field: Field) -> None:
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")

    call_command("purge_trash", skip_backup_check=True)

    assert Field.all_objects.filter(pk=field.pk).exists()
    assert not AuditEntry.objects.filter(action=AuditEntry.Action.PURGE).exists()


@pytest.mark.django_db
def test_purge_removes_report_pdfs(
    api_client: APIClient, user: User, field: Field, settings, tmp_path: Path
) -> None:
    settings.REPORT_CACHE_DIR = tmp_path
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=1,
        idempotency_key="job-pdf",
        params={},
        status=AnalysisJob.Status.COMPLETED,
        result={},
    )
    pdf = tmp_path / f"{job.pk}-20260801T000000.pdf"
    pdf.write_bytes(b"%PDF-fake")

    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")
    Field.all_objects.filter(pk=field.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )

    call_command("purge_trash", skip_backup_check=True)

    assert not pdf.exists()


@pytest.mark.django_db
def test_purge_requires_recent_backup(
    api_client: APIClient, user: User, field: Field, settings, tmp_path: Path
) -> None:
    import os
    import time

    settings.PURGE_BACKUP_MARKER = tmp_path / "last-backup.txt"
    api_client.force_authenticate(user)
    api_client.delete(f"/api/v1/fields/{field.pk}/")
    Field.all_objects.filter(pk=field.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )

    # Nessun marker: purge annullato.
    with pytest.raises(CommandError, match="backup recente"):
        call_command("purge_trash")
    assert Field.all_objects.filter(pk=field.pk).exists()

    # Marker piu' vecchio di 48h: purge annullato.
    marker = tmp_path / "last-backup.txt"
    marker.touch()
    old_time = time.time() - 49 * 3600
    os.utime(marker, (old_time, old_time))
    with pytest.raises(CommandError, match="backup recente"):
        call_command("purge_trash")

    # Marker fresco: purge eseguito.
    marker.touch()
    call_command("purge_trash")
    assert not Field.all_objects.filter(pk=field.pk).exists()


@pytest.mark.django_db
def test_hard_delete_without_purge_bypass_is_blocked_by_guard(field: Field) -> None:
    """Il guard DB blocca il DELETE hard senza SET LOCAL verdimetria.allow_purge."""
    with pytest.raises(DatabaseError, match="guard"):
        Field.all_objects.get(pk=field.pk).delete()


@pytest.mark.django_db
def test_audit_entries_are_append_only(field: Field) -> None:
    entry = AuditEntry.objects.create(
        action=AuditEntry.Action.DELETE, entity_type="field", entity_id=str(field.pk)
    )
    with pytest.raises(DatabaseError):
        entry.reason = "manomissione"
        entry.save()
    with pytest.raises(DatabaseError):
        entry.delete()


@pytest.mark.django_db
def test_job_owner_must_match_field_owner(user: User, field: Field) -> None:
    other = User.objects.create_user(email="other@example.com", password="StrongPass-2026!")
    with pytest.raises(IntegrityError):
        AnalysisJob.objects.create(
            field=field,
            owner=other,
            boundary_version=1,
            idempotency_key="owner-diverso",
            params={},
        )


@pytest.mark.django_db
def test_demo_field_soft_delete_blocked_at_db_level(user: User, field: Field) -> None:
    field.is_demo = True
    field.save(update_fields=("is_demo",))
    from django.db import connection

    with pytest.raises(DatabaseError):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE fields_field SET deleted_at = now() WHERE id = %s",
                [str(field.pk)],
            )


@pytest.mark.django_db
def test_boundary_versions_are_immutable(field: Field) -> None:
    boundary = field.boundaries.first()
    assert boundary is not None
    boundary.source = "upload"
    with pytest.raises(DatabaseError):
        boundary.save()


@pytest.mark.django_db
def test_job_status_check_constraint(field: Field, user: User) -> None:
    with pytest.raises(IntegrityError):
        job = AnalysisJob(
            field=field,
            owner=user,
            boundary_version=1,
            idempotency_key="status-bogus",
            params={},
            status="bogus",
        )
        job.save(force_insert=True)
