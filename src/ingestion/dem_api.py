"""
Copernicus DEM (GLO-30) via Process API CDSE.

Il DEM e' un dato statico (acquisizioni 2011-2015): lo scarichiamo una volta
per campo e le feature morfometriche (pendenza, esposizione) le calcoliamo
in locale con rasterio/numpy — niente servizi live nella pipeline del job.

Stessa OAuth e stesso builder della Process API gia' usati per Sentinel-2.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from requests_oauthlib import OAuth2Session

from src.domain import AnalysisArea
from src.ingestion.process_api import PROCESS_URL, build_process_request, get_oauth_session

DEM_COLLECTION = "dem"
DEM_RESOLUTION_M = 30
DEM_START_DATE = "2010-01-01"  # precede le acquisizioni GLO-30 (2011-2015)

# Output: quota in metri, singola banda FLOAT32, NaN fuori poligono.
DEM_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["DEM", "dataMask"] }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  if (sample.dataMask === 0) {
    return [NaN];
  }
  return [sample.DEM];
}
""".strip()


def build_dem_request(
    area: AnalysisArea,
    *,
    resolution_m: float = DEM_RESOLUTION_M,
) -> dict[str, Any]:
    """Payload Process API per il DEM sul poligono, CRS metrico locale."""
    return build_process_request(
        DEM_EVALSCRIPT,
        area,
        DEM_START_DATE,
        date.today().isoformat(),
        resolution_m=resolution_m,
        collection=DEM_COLLECTION,
        max_cloud_cover=100,  # irrilevante per il DEM, ma il builder lo richiede
    )


def fetch_dem(
    area: AnalysisArea,
    *,
    oauth: OAuth2Session | None = None,
    resolution_m: float = DEM_RESOLUTION_M,
) -> bytes:
    """GeoTIFF FLOAT32 della quota (m) ritagliato sul poligono dell'area."""
    session = oauth if oauth is not None else get_oauth_session()
    response = session.post(
        PROCESS_URL,
        json=build_dem_request(area, resolution_m=resolution_m),
        headers={"Accept": "image/tiff"},
    )
    response.raise_for_status()
    return response.content
