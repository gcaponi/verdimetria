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

import requests
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# Evalscript NDVI raw, output a singola banda float — nessuna ambiguità
# visualizzazione/raw come nei layer preconfigurati.
NDVI_RAW_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "dataMask"] }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-9);
  return [ndvi];
}
""".strip()


def _get_oauth_session() -> OAuth2Session:
    client_id = os.environ["CDSE_CLIENT_ID"]
    client_secret = os.environ["CDSE_CLIENT_SECRET"]

    client = BackendApplicationClient(client_id=client_id)
    oauth = OAuth2Session(client=client)
    oauth.fetch_token(token_url=TOKEN_URL, client_secret=client_secret, include_client_id=True)
    return oauth


def fetch_processed_layer(
    evalscript: str,
    bbox_wgs84: list[float],
    start_date: str,
    end_date: str,
    output_path: str,
    width: int = 512,
    height: int = 512,
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
    oauth = _get_oauth_session()

    request_body = {
        "input": {
            "bounds": {
                "bbox": bbox_wgs84,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "type": collection,
                "dataFilter": {
                    "timeRange": {"from": f"{start_date}T00:00:00Z", "to": f"{end_date}T23:59:59Z"},
                    "maxCloudCoverage": max_cloud_cover,
                },
            }],
        },
        "output": {"width": width, "height": height, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": evalscript,
    }

    response = oauth.post(PROCESS_URL, json=request_body, headers={"Accept": "image/tiff"})
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def fetch_ndvi(bbox_wgs84: list[float], start_date: str, end_date: str, output_path: str, **kwargs) -> None:
    """Scorciatoia: NDVI raw (FLOAT32, una banda) su L2A per l'area/periodo dati."""
    fetch_processed_layer(NDVI_RAW_EVALSCRIPT, bbox_wgs84, start_date, end_date, output_path, **kwargs)
