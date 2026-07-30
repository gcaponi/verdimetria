"""Task Celery per l'esecuzione asincrona degli AnalysisJob."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils import timezone
from requests.exceptions import RequestException, Timeout

from backend.fields.insights import generate_insights
from backend.fields.models import AnalysisJob
from backend.fields.pipeline import (
    build_field_analysis,
    parse_statistics,
    summarize_catalog,
    summarize_vegetation,
)
from src.domain import AnalysisArea
from src.ingestion.catalog_api import fetch_catalog_items
from src.ingestion.dem_api import fetch_dem
from src.ingestion.process_api import get_oauth_session
from src.ingestion.statistical_api import fetch_ndvi_statistics
from src.landcover import compute_land_cover
from src.terrain import compute_morphometry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

CLC_PLUS_RASTER_ENV = "CLC_PLUS_RASTER_PATH"


def _compute_terrain(area: AnalysisArea, oauth: Any) -> dict[str, Any]:
    """Morfometria da TINITALY 10 m se la cache e' configurata, fallback CDSE 30 m."""
    cache_dir = os.getenv("TINITALY_CACHE_DIR", "").strip()
    if cache_dir:
        from src.ingestion.tinitaly import compute_morphometry_tinitaly

        try:
            return compute_morphometry_tinitaly(area, Path(cache_dir))
        except Exception as error:
            logger.warning("tinitaly_fallback: %s", error)
    dem = fetch_dem(area, oauth=oauth)
    return compute_morphometry(dem, area)


def _compute_land_cover_if_configured(area: AnalysisArea) -> dict[str, Any] | None:
    """Blocco landCover opzionale: attivo solo se il raster CLC+ e' deployato."""
    raster_path = os.getenv(CLC_PLUS_RASTER_ENV, "").strip()
    if not raster_path:
        logger.info("landcover_skipped: %s non configurata", CLC_PLUS_RASTER_ENV)
        return None
    return compute_land_cover(raster_path, area)


def _set_progress(job: AnalysisJob, step: str) -> None:
    job.progress_step = step
    job.save(update_fields=("progress_step",))


def _mark_failed(job: AnalysisJob, message: str) -> None:
    job.status = AnalysisJob.Status.FAILED
    job.error = message
    job.completed_at = timezone.now()
    job.save(update_fields=("status", "error", "completed_at"))
    logger.warning("analysis_job_failed job=%s error=%s", job.pk, message)


def _execute(job: AnalysisJob) -> dict[str, Any]:
    params = job.params
    field = job.field
    boundary = field.boundaries.filter(version=params["boundary_version"]).first()
    if boundary is None:
        raise ValueError(
            f"Il confine v{params['boundary_version']} non esiste piu' per questo campo"
        )
    area = AnalysisArea.from_geojson(
        field.name,
        json.loads(boundary.geometry.geojson),
    )

    # Una sola sessione OAuth (un solo token) per tutte le chiamate CDSE del job.
    oauth = get_oauth_session()

    _set_progress(job, "catalog")
    items = fetch_catalog_items(
        area,
        params["start_date"],
        params["end_date"],
        max_cloud_cover=params["max_cloud_cover"],
        oauth=oauth,
    )
    catalog = summarize_catalog(items)

    _set_progress(job, "statistical")
    statistics = fetch_ndvi_statistics(
        area,
        params["start_date"],
        params["end_date"],
        resolution_m=params["resolution_m"],
        max_cloud_cover=params["max_cloud_cover"],
        oauth=oauth,
    )
    points = parse_statistics(statistics)
    if not points:
        raise ValueError("Nessuna osservazione NDVI valida nel periodo selezionato")
    vegetation = summarize_vegetation(points)

    _set_progress(job, "terrain")
    terrain = _compute_terrain(area, oauth)

    _set_progress(job, "landcover")
    land_cover = _compute_land_cover_if_configured(area)

    _set_progress(job, "ai")
    ai = generate_insights({
        "areaHectares": float(boundary.area_hectares),
        "startDate": params["start_date"],
        "endDate": params["end_date"],
        "catalog": catalog,
        "vegetation": vegetation,
        "crop": job.field.crop,
    })

    return build_field_analysis(
        analysis_id=job.pk.hex[:16],
        generated_at=timezone.now().isoformat(),
        area=area,
        area_hectares=float(boundary.area_hectares),
        utm_crs=boundary.metric_crs,
        start_date=params["start_date"],
        end_date=params["end_date"],
        resolution_m=params["resolution_m"],
        catalog=catalog,
        vegetation=vegetation,
        terrain=terrain,
        land_cover=land_cover,
        ai=ai,
    )


@shared_task(bind=True, max_retries=MAX_RETRIES)
def run_analysis_job(self: Any, job_id: str) -> None:
    with transaction.atomic():
        job = (
            AnalysisJob.objects.select_for_update()
            .select_related("field")
            .get(pk=job_id)
        )
        if job.status == AnalysisJob.Status.COMPLETED:
            return
        job.status = AnalysisJob.Status.RUNNING
        job.progress_step = ""
        job.attempts += 1
        job.celery_task_id = self.request.id or ""
        if job.started_at is None:
            job.started_at = timezone.now()
        job.save(
            update_fields=(
                "status",
                "progress_step",
                "attempts",
                "celery_task_id",
                "started_at",
            )
        )

    try:
        result = _execute(job)
    except (ValueError, KeyError) as error:
        # Errori definitivi (parametri, budget pixel, credenziali assenti): niente retry.
        _mark_failed(job, str(error))
        return
    except (RequestException, Timeout) as error:
        countdown = min(2 ** self.request.retries * 30, 300)
        try:
            raise self.retry(exc=error, countdown=countdown)
        except MaxRetriesExceededError:
            _mark_failed(
                job,
                f"Servizio dati non raggiungibile dopo {job.attempts} tentativi: {error}",
            )
            return

    job.status = AnalysisJob.Status.COMPLETED
    job.progress_step = "done"
    job.result = result
    job.error = ""
    job.completed_at = timezone.now()
    job.save(update_fields=("status", "progress_step", "result", "error", "completed_at"))
