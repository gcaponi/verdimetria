"""Trasformazioni pure Catalog/Statistical → contratto FieldAnalysis."""

from __future__ import annotations

from typing import Any

from src.domain import AnalysisArea
from src.ingestion.catalog_api import CatalogItem

DISCLAIMER = (
    "Analisi osservativa da satellite: evidenzia pattern da verificare sul campo "
    "e non sostituisce sopralluogo, laboratorio o consulenza agronomica."
)

CATALOG_PROVENANCE = {
    "provider": "Copernicus Data Space Ecosystem",
    "dataset": "Sentinel-2 L2A",
    "services": ["Catalog API", "Statistical API"],
    "quality": "SCL cloud/shadow mask + dataMask",
}

MAX_CATALOG_ITEMS = 12


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _percentile(percentiles: Any, percentile: int) -> float | None:
    if not _is_record(percentiles):
        return None
    for key in (str(percentile), f"{percentile}.0"):
        value = _number(percentiles.get(key))
        if value is not None:
            return _round(value)
    return None


def parse_statistics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Statistical API → punti NDVI per intervallo (mirrors Worker parseStatistics)."""
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        return []

    points: list[dict[str, Any]] = []
    for entry in raw_data:
        if not _is_record(entry):
            continue
        interval = entry.get("interval")
        outputs = entry.get("outputs")
        if not _is_record(interval) or not _is_record(outputs):
            continue
        ndvi = outputs.get("ndvi")
        if not _is_record(ndvi):
            continue
        bands = ndvi.get("bands")
        if not _is_record(bands):
            continue
        band = bands.get("B0")
        if not _is_record(band):
            continue
        stats = band.get("stats")
        if not _is_record(stats):
            continue

        from_iso = interval.get("from")
        to_iso = interval.get("to")
        mean = _number(stats.get("mean"))
        min_value = _number(stats.get("min"))
        max_value = _number(stats.get("max"))
        st_dev = _number(stats.get("stDev"))
        sample_count = _number(stats.get("sampleCount")) or 0
        no_data_count = _number(stats.get("noDataCount")) or 0
        if (
            not isinstance(from_iso, str)
            or not isinstance(to_iso, str)
            or mean is None
            or min_value is None
            or max_value is None
            or st_dev is None
            or sample_count - no_data_count <= 0
        ):
            continue

        points.append({
            "date": to_iso[:10],
            "from": from_iso,
            "to": to_iso,
            "mean": _round(mean),
            "min": _round(min_value),
            "max": _round(max_value),
            "stDev": _round(st_dev),
            "p10": _percentile(stats.get("percentiles"), 10),
            "p50": _percentile(stats.get("percentiles"), 50),
            "p90": _percentile(stats.get("percentiles"), 90),
            "validPixels": max(0, round(sample_count - no_data_count)),
        })
    return points


def summarize_vegetation(points: list[dict[str, Any]]) -> dict[str, Any]:
    means = [point["mean"] for point in points]
    recent = means[-3:]
    previous = means[-6:-3]
    trend = _round(_average(recent) - _average(previous)) if previous else None
    return {
        "points": points,
        "current": means[-1] if means else None,
        "average": _round(_average(means)),
        "min": min(means) if means else 0,
        "max": max(means) if means else 0,
        "trend": trend,
        "validObservations": len(points),
        "totalValidPixels": sum(point["validPixels"] for point in points),
    }


def summarize_catalog(items: list[CatalogItem]) -> dict[str, Any]:
    sorted_items = sorted(items, key=lambda item: item.acquired_at, reverse=True)
    summary_items = [
        {
            "id": item.item_id,
            "acquiredAt": item.acquired_at,
            "cloudCover": _round(item.cloud_cover, 1) if item.cloud_cover is not None else None,
        }
        for item in sorted_items[:MAX_CATALOG_ITEMS]
    ]
    cloud_values = [item.cloud_cover for item in items if item.cloud_cover is not None]
    return {
        "sceneCount": len(items),
        "latestAcquisition": sorted_items[0].acquired_at if sorted_items else None,
        "meanCloudCover": _round(_average(cloud_values), 1) if cloud_values else None,
        "items": summary_items,
    }


def build_field_analysis(
    *,
    analysis_id: str,
    generated_at: str,
    area: AnalysisArea,
    area_hectares: float,
    utm_crs: str,
    start_date: str,
    end_date: str,
    resolution_m: int,
    catalog: dict[str, Any],
    vegetation: dict[str, Any],
    ai: dict[str, Any],
    terrain: dict[str, Any],
    land_cover: dict[str, Any] | None = None,
) -> dict[str, Any]:
    centroid = area.geometry.centroid
    provenance = [
        CATALOG_PROVENANCE,
        {
            "provider": terrain.get("source", "Copernicus DEM GLO-30"),
            "dataset": f"Digital Elevation Model {terrain.get('resolutionMeters', 30)} m",
            "services": ["Download tile lazy" if "TINITALY" in terrain.get("source", "") else "Process API"],
            "quality": "Feature morfometriche calcolate localmente sul poligono",
        },
        {
            "provider": ai["provider"],
            "dataset": ai["model"],
            "services": ["Interpretazione strutturata"],
            "quality": "Solo metriche aggregate; nessuna prescrizione automatica",
        },
    ]
    if land_cover is not None:
        provenance.append({
            "provider": "Copernicus Land Monitoring Service",
            "dataset": "CLC+ Backbone 2021 raster 10 m",
            "services": ["Download WEkEO (una-tantum)"],
            "quality": "Statistiche zonali calcolate localmente sul poligono",
        })
    result = {
        "status": "ready",
        "analysisId": analysis_id,
        "generatedAt": generated_at,
        "period": {"from": start_date, "to": end_date},
        "area": {
            "hectares": _round(area_hectares, 2),
            "centroid": [_round(centroid.x, 6), _round(centroid.y, 6)],
            "utmCrs": utm_crs,
            "resolutionMeters": resolution_m,
        },
        "catalog": catalog,
        "vegetation": vegetation,
        "terrain": terrain,
        "ai": ai,
        "provenance": provenance,
        "disclaimer": DISCLAIMER,
    }
    if land_cover is not None:
        result["landCover"] = land_cover
    return result
