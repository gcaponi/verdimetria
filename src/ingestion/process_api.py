"""
Client per la Process API di Sentinel Hub (Copernicus Data Space Ecosystem).

Perché questo modulo esiste, oltre a sentinel_hub_wms.py: i layer preconfigurati
nella tua Configuration Instance (Agricoltura, NDVI, Geologia...) sono
composti pensati per la visualizzazione — es. "Agriculture" è letteralmente
bande 11/8A/2 mappate su RGB per l'ispezione visiva, su dati L1C (non
corretti atmosfericamente). Non sono adatti a un'analisi quantitativa.

La Process API risolve il problema alla radice: invii TU l'evalscript,
specifichi output FLOAT32, e scegli tu la collezione (L2A per dati corretti
atmosfericamente). Nessuna ambiguità su cosa stai davvero scaricando.

Richiede le stesse credenziali OAuth già configurate in .env
(CDSE_CLIENT_ID / CDSE_CLIENT_SECRET) usate da sentinel2_cdse.py.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Protocol, cast

from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
from shapely.geometry import mapping

from src.domain import AnalysisArea

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# Evalscript NDVI raw, output a singola banda float — nessuna ambiguità
# visualizzazione/raw come nei layer preconfigurati.
NDVI_RAW_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
        input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
    const invalidScl = [0, 1, 2, 3, 8, 9, 10, 11].includes(sample.SCL);
    if (sample.dataMask === 0 || invalidScl) {
        return [NaN];
    }
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-9);
  return [ndvi];
}
""".strip()


class OAuthTokenFetcher(Protocol):
    def fetch_token(
        self,
        *,
        token_url: str,
        client_secret: str,
        include_client_id: bool,
    ) -> dict[str, Any]: ...


def get_oauth_session() -> OAuth2Session:
    client_id = os.environ["CDSE_CLIENT_ID"]
    client_secret = os.environ["CDSE_CLIENT_SECRET"]

    client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=client)
    token_fetcher = cast(OAuthTokenFetcher, oauth)
    token_fetcher.fetch_token(
        token_url=TOKEN_URL,
        client_secret=client_secret,
        include_client_id=True,
    )
    return oauth


def crs_uri(target_crs: str) -> str:
    authority, separator, code = target_crs.upper().partition(":")
    if authority != "EPSG" or separator != ":" or not code.isdigit():
        raise ValueError("Il CRS di output deve avere formato EPSG:<codice>")
    return f"http://www.opengis.net/def/crs/EPSG/0/{code}"


def build_process_request(
    evalscript: str,
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    *,
    resolution_m: float = 10,
    target_crs: str | None = None,
    max_pixels: int = 25_000_000,
    collection: str = "sentinel-2-l2a",
    max_cloud_cover: int = 20,
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as error:
        raise ValueError("Le date devono avere formato YYYY-MM-DD") from error

    if start > end:
        raise ValueError("L'intervallo temporale deve avere una data iniziale non successiva alla finale")
    if not 0 <= max_cloud_cover <= 100:
        raise ValueError("La copertura nuvolosa deve essere compresa tra 0 e 100")

    metric_crs = target_crs or area.local_utm_crs()
    dimensions = area.raster_dimensions(resolution_m, metric_crs, max_pixels)
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
                    "timeRange": {
                        "from": f"{start_date}T00:00:00Z",
                        "to": f"{end_date}T23:59:59Z",
                    },
                    "maxCloudCoverage": max_cloud_cover,
                },
            }],
        },
        "output": {
            "width": dimensions.width,
            "height": dimensions.height,
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/tiff"},
            }],
        },
        "evalscript": evalscript,
    }


def fetch_processed_layer(
    evalscript: str,
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    output_path: str,
    resolution_m: float = 10,
    target_crs: str | None = None,
    max_pixels: int = 25_000_000,
    collection: str = "sentinel-2-l2a",  # L2A = corretto atmosfericamente, a differenza del preset "Agriculture" (L1C)
    max_cloud_cover: int = 20,
) -> None:
    """
    Richiede un layer processato secondo il TUO evalscript (non un preset),
    su dati L2A per default. Ritorna quello che l'evalscript definisce (per
    NDVI_RAW_EVALSCRIPT: un GeoTIFF a singola banda float32 con NDVI reale).

    NOTA: non testato con una chiamata di rete reale in questo ambiente
    (dominio dataspace.copernicus.eu non raggiungibile dalla sandbox).
    """
    request_body = build_process_request(
        evalscript,
        area,
        start_date,
        end_date,
        resolution_m=resolution_m,
        target_crs=target_crs,
        max_pixels=max_pixels,
        collection=collection,
        max_cloud_cover=max_cloud_cover,
    )
    oauth = get_oauth_session()

    response = oauth.post(PROCESS_URL, json=request_body, headers={"Accept": "image/tiff"})
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def fetch_ndvi(
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    output_path: str,
    **kwargs: Any,
) -> None:
    """Scorciatoia: NDVI raw (FLOAT32, una banda) su L2A per l'area/periodo dati."""
    fetch_processed_layer(NDVI_RAW_EVALSCRIPT, area, start_date, end_date, output_path, **kwargs)
