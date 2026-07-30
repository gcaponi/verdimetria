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
    "quality": "SCL cloud/shadow mask + dataMask su NDVI e NDMI",
}

MAX_CATALOG_ITEMS = 12

# Vigor-class thresholds on NDVI: MVP convention, not agronomic truth.
VIGOR_WEAK_MAX_NDVI = 0.3  # NDVI below this -> weak vegetation
VIGOR_VIGOROUS_MIN_NDVI = 0.5  # NDVI above this -> vigorous vegetation

VIGOR_THRESHOLDS_NOTE = (
    "Classi di vigore da soglie NDVI convenzionali MVP "
    f"(debole <{VIGOR_WEAK_MAX_NDVI}, intermedia {VIGOR_WEAK_MAX_NDVI}-"
    f"{VIGOR_VIGOROUS_MIN_NDVI}, vigorosa >{VIGOR_VIGOROUS_MIN_NDVI}): "
    "non sono una verita' agronomica."
)

# Point keys parsed from the Statistical response but only used to derive the
# ndmi/variability blocks: they stay out of the public vegetation points.
_DERIVED_POINT_KEYS = ("ndmi", "histogram")


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


def _output_band(outputs: dict[str, Any], output_id: str) -> dict[str, Any] | None:
    output = outputs.get(output_id)
    if not _is_record(output):
        return None
    bands = output.get("bands")
    if not _is_record(bands):
        return None
    band = bands.get("B0")
    return band if _is_record(band) else None


def _parse_band_stats(stats: Any) -> dict[str, Any] | None:
    """Stats block of one output band → flat point fields, None when invalid."""
    if not _is_record(stats):
        return None
    mean = _number(stats.get("mean"))
    min_value = _number(stats.get("min"))
    max_value = _number(stats.get("max"))
    st_dev = _number(stats.get("stDev"))
    sample_count = _number(stats.get("sampleCount")) or 0
    no_data_count = _number(stats.get("noDataCount")) or 0
    if (
        mean is None
        or min_value is None
        or max_value is None
        or st_dev is None
        or sample_count - no_data_count <= 0
    ):
        return None
    return {
        "mean": _round(mean),
        "min": _round(min_value),
        "max": _round(max_value),
        "stDev": _round(st_dev),
        "p10": _percentile(stats.get("percentiles"), 10),
        "p50": _percentile(stats.get("percentiles"), 50),
        "p90": _percentile(stats.get("percentiles"), 90),
        "validPixels": max(0, round(sample_count - no_data_count)),
    }


def _parse_histogram(histogram: Any) -> dict[str, Any] | None:
    """Statistical API histogram → {bins, underflowCount, overflowCount} or None."""
    if not _is_record(histogram):
        return None
    raw_bins = histogram.get("bins")
    if not isinstance(raw_bins, list):
        return None
    bins: list[dict[str, float]] = []
    for raw_bin in raw_bins:
        if not _is_record(raw_bin):
            continue
        low_edge = _number(raw_bin.get("lowEdge"))
        high_edge = _number(raw_bin.get("highEdge"))
        count = _number(raw_bin.get("count"))
        if low_edge is None or high_edge is None or count is None:
            continue
        bins.append({"lowEdge": low_edge, "highEdge": high_edge, "count": count})
    if not bins:
        return None
    return {
        "bins": bins,
        "underflowCount": _number(histogram.get("underflowCount")) or 0,
        "overflowCount": _number(histogram.get("overflowCount")) or 0,
    }


def parse_statistics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Statistical API → NDVI points per interval (mirrors Worker parseStatistics).

    Each point also carries the aux keys "ndmi" (same stats layout, None when
    absent) and "histogram" (NDVI bin counts, None when absent), used downstream
    to derive the ndmi/variability blocks.
    """
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
        ndvi_band = _output_band(outputs, "ndvi")
        if ndvi_band is None:
            continue
        stats = _parse_band_stats(ndvi_band.get("stats"))

        from_iso = interval.get("from")
        to_iso = interval.get("to")
        if stats is None or not isinstance(from_iso, str) or not isinstance(to_iso, str):
            continue

        ndmi_band = _output_band(outputs, "ndmi")
        points.append({
            "date": to_iso[:10],
            "from": from_iso,
            "to": to_iso,
            **stats,
            "ndmi": _parse_band_stats(ndmi_band.get("stats")) if ndmi_band else None,
            "histogram": _parse_histogram(ndvi_band.get("histogram")),
        })
    return points


def _summarize_series(points: list[dict[str, Any]]) -> dict[str, Any]:
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


def summarize_vegetation(points: list[dict[str, Any]]) -> dict[str, Any]:
    return _summarize_series(points)


def summarize_ndmi(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """NDMI (moisture) block mirroring the vegetation one; None when absent."""
    ndmi_points = [
        {"date": point["date"], "from": point["from"], "to": point["to"], **point["ndmi"]}
        for point in points
        if _is_record(point.get("ndmi"))
    ]
    if not ndmi_points:
        return None
    return _summarize_series(ndmi_points)


def compute_vigor_variability(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    """% of the field in the 3 vigor classes on the latest valid NDVI observation.

    Real pixel counts from the NDVI histogram when available; otherwise a coarse
    approximation interpolated from the percentiles, flagged in `method`.
    """
    if not points:
        return None
    latest = points[-1]
    histogram = latest.get("histogram")
    if _is_record(histogram):
        classes = _classes_from_histogram(histogram)
        method = "histogram"
    else:
        classes = _classes_from_percentiles(latest)
        method = "percentile-approximation"
    if classes is None:
        return None
    weak, intermediate, vigorous = classes
    return {
        "date": latest["date"],
        "validPixels": latest["validPixels"],
        "weak": _round(weak, 1),
        "intermediate": _round(intermediate, 1),
        "vigorous": _round(vigorous, 1),
        "method": method,
        "thresholds": {"weakMax": VIGOR_WEAK_MAX_NDVI, "vigorousMin": VIGOR_VIGOROUS_MIN_NDVI},
        "note": VIGOR_THRESHOLDS_NOTE,
    }


def _classes_from_histogram(histogram: dict[str, Any]) -> tuple[float, float, float] | None:
    # Underflow/overflow counts can only come from NDVI noise outside [-1, 1]:
    # underflow is certainly weak, overflow certainly vigorous.
    weak = float(histogram["underflowCount"])
    vigorous = float(histogram["overflowCount"])
    intermediate = 0.0
    for histogram_bin in histogram["bins"]:
        bin_weak, bin_intermediate, bin_vigorous = _split_bin(
            histogram_bin["lowEdge"], histogram_bin["highEdge"], histogram_bin["count"]
        )
        weak += bin_weak
        intermediate += bin_intermediate
        vigorous += bin_vigorous
    total = weak + intermediate + vigorous
    if total <= 0:
        return None
    return 100 * weak / total, 100 * intermediate / total, 100 * vigorous / total


def _split_bin(low_edge: float, high_edge: float, count: float) -> tuple[float, float, float]:
    """Split a bin count across the vigor classes by proportional overlap.

    Exact with the requested 0.1-wide bins (thresholds fall on bin edges);
    degrades to a within-bin uniform assumption if thresholds change.
    """
    width = high_edge - low_edge
    if width <= 0:
        return 0.0, 0.0, 0.0
    weak = max(0.0, min(high_edge, VIGOR_WEAK_MAX_NDVI) - low_edge) / width * count
    vigorous = max(0.0, high_edge - max(low_edge, VIGOR_VIGOROUS_MIN_NDVI)) / width * count
    return weak, count - weak - vigorous, vigorous


def _classes_from_percentiles(point: dict[str, Any]) -> tuple[float, float, float] | None:
    """Fallback: piecewise-linear CDF through min/p10/p50/p90/max."""
    anchors = [(point["min"], 0.0)]
    anchors.extend(
        (point[key], percentile)
        for key, percentile in (("p10", 10.0), ("p50", 50.0), ("p90", 90.0))
        if point.get(key) is not None
    )
    anchors.append((point["max"], 100.0))
    if len(anchors) < 3:
        return None
    weak = _interpolated_cdf(anchors, VIGOR_WEAK_MAX_NDVI)
    vigorous_start = _interpolated_cdf(anchors, VIGOR_VIGOROUS_MIN_NDVI)
    return weak, max(0.0, vigorous_start - weak), max(0.0, 100.0 - vigorous_start)


def _interpolated_cdf(anchors: list[tuple[float, float]], value: float) -> float:
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (low_value, low_pct), (high_value, high_pct) in zip(anchors, anchors[1:]):
        if low_value <= value <= high_value:
            if high_value == low_value:
                return high_pct
            return low_pct + (high_pct - low_pct) * (value - low_value) / (high_value - low_value)
    return anchors[-1][1]


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
        "vegetation": _public_vegetation(vegetation),
        "ndmi": summarize_ndmi(vegetation.get("points", [])),
        "variability": compute_vigor_variability(vegetation.get("points", [])),
        "terrain": terrain,
        "ai": ai,
        "provenance": provenance,
        "disclaimer": DISCLAIMER,
    }
    if land_cover is not None:
        result["landCover"] = land_cover
    return result


def _public_vegetation(vegetation: dict[str, Any]) -> dict[str, Any]:
    """Vegetation block without the aux point keys used for derived blocks."""
    points = vegetation.get("points", [])
    public_points = [
        {key: value for key, value in point.items() if key not in _DERIVED_POINT_KEYS}
        for point in points
    ]
    return {**vegetation, "points": public_points}
