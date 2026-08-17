"""Costruzione parametri e chiave idempotente per gli AnalysisJob."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from backend.fields.models import Field

DEFAULT_MAX_CLOUD_COVER = 20
DEFAULT_END_LAG_DAYS = 3
MAX_PERIOD_DAYS = 731
LARGE_FIELD_THRESHOLD_HECTARES = 500
DEFAULT_RESOLUTION_M = 10
LARGE_FIELD_RESOLUTION_M = 20


def resolution_for_area(area_hectares: float) -> int:
    if area_hectares > LARGE_FIELD_THRESHOLD_HECTARES:
        return LARGE_FIELD_RESOLUTION_M
    return DEFAULT_RESOLUTION_M


def default_period(today: date | None = None) -> tuple[str, str]:
    """Ultimo anno fino a 3 giorni fa (ritardo tipico di pubblicazione L2A)."""
    reference = today or date.today()
    end = reference - timedelta(days=DEFAULT_END_LAG_DAYS)
    try:
        start = end.replace(year=end.year - 1)
    except ValueError:
        # 29 febbraio → 28 febbraio dell'anno precedente
        start = end.replace(year=end.year - 1, day=28)
    return start.isoformat(), end.isoformat()


def parse_iso_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} deve avere formato YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} deve avere formato YYYY-MM-DD") from error
    return value


def build_job_params(
    field: Field,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    boundary = field.boundaries.first()
    if boundary is None:
        raise ValueError("Il campo non ha un confine salvato")

    default_start, default_end = default_period()
    start = parse_iso_date(start_date, "start_date") if start_date else default_start
    end = parse_iso_date(end_date, "end_date") if end_date else default_end
    if start >= end:
        raise ValueError("L'intervallo temporale non e' valido")
    span = date.fromisoformat(end) - date.fromisoformat(start)
    if span.days > MAX_PERIOD_DAYS:
        raise ValueError("L'intervallo temporale non puo' superare due anni")

    return {
        "start_date": start,
        "end_date": end,
        "max_cloud_cover": DEFAULT_MAX_CLOUD_COVER,
        "resolution_m": resolution_for_area(float(boundary.area_hectares)),
        "boundary_version": boundary.version,
    }


def compute_idempotency_key(field: Field, params: dict[str, Any]) -> str:
    raw = "|".join([
        str(field.pk),
        str(params["boundary_version"]),
        str(params["start_date"]),
        str(params["end_date"]),
        str(params["resolution_m"]),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
