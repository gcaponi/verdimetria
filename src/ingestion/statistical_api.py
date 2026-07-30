"""Client for NDVI/NDMI statistics via the Sentinel Hub Statistical API on CDSE."""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence, cast

from shapely.geometry import mapping

from src.domain import AnalysisArea
from src.ingestion.process_api import crs_uri, get_oauth_session

STATISTICAL_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"

# NDVI histogram requested for the vigor classes: bin edges stay aligned with
# the MVP vigor thresholds (0.3 / 0.5), so every bin falls in a single class.
NDVI_HISTOGRAM_BINS = 20
NDVI_HISTOGRAM_LOW_EDGE = -1.0
NDVI_HISTOGRAM_HIGH_EDGE = 1.0

VEGETATION_STATISTICS_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "ndmi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: ["ndvi", "ndmi"] }
    ]
  };
}
function evaluatePixel(sample) {
  const invalidScl = [0, 1, 2, 3, 8, 9, 10, 11].includes(sample.SCL);
  const ndviDenominator = sample.B08 + sample.B04;
  const ndmiDenominator = sample.B08 + sample.B11;
  const masked = sample.dataMask === 1 && !invalidScl;
  const ndviValid = masked && ndviDenominator !== 0;
  const ndmiValid = masked && ndmiDenominator !== 0;
  return {
    ndvi: [ndviValid ? (sample.B08 - sample.B04) / ndviDenominator : 0],
    ndmi: [ndmiValid ? (sample.B08 - sample.B11) / ndmiDenominator : 0],
    dataMask: [ndviValid ? 1 : 0, ndmiValid ? 1 : 0]
  };
}
""".strip()


def build_statistical_request(
    evalscript: str,
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    *,
    aggregation_interval: str = "P10D",
    resolution_m: float = 10,
    target_crs: str | None = None,
    max_pixels: int = 25_000_000,
    collection: str = "sentinel-2-l2a",
    max_cloud_cover: int = 20,
    percentiles: Sequence[float] = (10, 50, 90),
    last_interval_behavior: str = "SHORTEN",
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as error:
        raise ValueError("Le date devono avere formato YYYY-MM-DD") from error

    if start > end:
        raise ValueError("L'intervallo temporale deve avere una data iniziale non successiva alla finale")
    if not aggregation_interval:
        raise ValueError("L'intervallo di aggregazione non puo' essere vuoto")
    if not 0 <= max_cloud_cover <= 100:
        raise ValueError("La copertura nuvolosa deve essere compresa tra 0 e 100")
    if not percentiles or any(percentile < 0 or percentile > 100 for percentile in percentiles):
        raise ValueError("I percentili devono essere compresi tra 0 e 100")
    if last_interval_behavior not in {"SKIP", "SHORTEN", "EXTEND"}:
        raise ValueError("Il comportamento dell'ultimo intervallo non e' valido")

    metric_crs = target_crs or area.local_utm_crs()
    area.raster_dimensions(resolution_m, metric_crs, max_pixels)
    projected_geometry = mapping(area.projected_geometry(metric_crs))

    return {
        "input": {
            "bounds": {
                "geometry": projected_geometry,
                "properties": {"crs": crs_uri(metric_crs)},
            },
            "data": [{
                "type": collection,
                "dataFilter": {
                    "mosaickingOrder": "leastCC",
                    "maxCloudCoverage": max_cloud_cover,
                },
            }],
        },
        "aggregation": {
            "timeRange": {
                "from": f"{start_date}T00:00:00Z",
                "to": f"{end_date}T23:59:59Z",
            },
            "aggregationInterval": {
                "of": aggregation_interval,
                "lastIntervalBehavior": last_interval_behavior,
            },
            "evalscript": evalscript,
            "resx": resolution_m,
            "resy": resolution_m,
        },
        "calculations": _index_calculations(percentiles),
    }


def _index_calculations(percentiles: Sequence[float]) -> dict[str, Any]:
    """Statistics for both indices; NDVI also carries the vigor-class histogram."""
    statistics = {"default": {"percentiles": {"k": list(percentiles)}}}
    return {
        "ndvi": {
            "statistics": statistics,
            "histograms": {
                "default": {
                    "nBins": NDVI_HISTOGRAM_BINS,
                    "lowEdge": NDVI_HISTOGRAM_LOW_EDGE,
                    "highEdge": NDVI_HISTOGRAM_HIGH_EDGE,
                },
            },
        },
        "ndmi": {"statistics": statistics},
    }


def fetch_ndvi_statistics(
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    *,
    oauth: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """NDVI+NDMI statistics from a single request; `oauth` reuses a session."""
    request_body = build_statistical_request(
        VEGETATION_STATISTICS_EVALSCRIPT,
        area,
        start_date,
        end_date,
        **kwargs,
    )
    oauth = oauth if oauth is not None else get_oauth_session()
    response = oauth.post(
        STATISTICAL_URL,
        json=request_body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("La Statistical API ha restituito un payload JSON non valido")
    return cast(dict[str, Any], payload)