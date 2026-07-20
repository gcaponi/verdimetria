"""Client per statistiche NDVI tramite Sentinel Hub Statistical API su CDSE."""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence, cast

from shapely.geometry import mapping

from src.domain import AnalysisArea
from src.ingestion.process_api import crs_uri, get_oauth_session

STATISTICAL_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"

NDVI_STATISTICS_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  const invalidScl = [0, 1, 2, 3, 8, 9, 10, 11].includes(sample.SCL);
  const denominator = sample.B08 + sample.B04;
  const valid = sample.dataMask === 1 && !invalidScl && denominator !== 0;
  return {
    ndvi: [valid ? (sample.B08 - sample.B04) / denominator : 0],
    dataMask: [valid ? 1 : 0]
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
        "calculations": {
            "ndvi": {
                "statistics": {
                    "default": {
                        "percentiles": {"k": list(percentiles)},
                    },
                },
            },
        },
    }


def fetch_ndvi_statistics(
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    **kwargs: Any,
) -> dict[str, Any]:
    request_body = build_statistical_request(
        NDVI_STATISTICS_EVALSCRIPT,
        area,
        start_date,
        end_date,
        **kwargs,
    )
    oauth = get_oauth_session()
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