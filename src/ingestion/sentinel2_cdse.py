"""
Client Sentinel-2 via Copernicus Data Space Ecosystem (CDSE).

IMPORTANTE: se hai incontrato tutorial o codice che usa `sentinelsat`, è
superato — quella libreria parlava con il vecchio Copernicus Open Access Hub
(SciHub), chiuso definitivamente. Il sostituto ufficiale è CDSE, con API
diverse (STAC per la ricerca, OData/Zipper per il download).

Qui usiamo `cdse-client` (libreria di terze parti non ufficiale, ma attiva
e allineata alle API attuali di CDSE) invece di reimplementare OAuth+STAC
a mano.

SETUP RICHIESTO (fuori da questo codice):
    1. Registrati gratuitamente su https://dataspace.copernicus.eu/
    2. Crea un OAuth client (Dashboard -> genera client_id/client_secret)
    3. Metti le credenziali in un file .env (vedi .env.example nella root
       del progetto) come CDSE_CLIENT_ID e CDSE_CLIENT_SECRET

NOTA: il dominio dataspace.copernicus.eu non è raggiungibile dalla sandbox
in cui questo modulo è stato scritto, quindi la chiamata di rete non è stata
validata live — solo l'import della libreria e l'uso base dell'API secondo
la sua documentazione ufficiale. Testala per prima cosa sulla tua macchina.
"""

from __future__ import annotations

import os

from cdse import CDSEClient


def search_sentinel2(
    bbox_wgs84: list[float],
    start_date: str,
    end_date: str,
    cloud_cover_max: int = 20,
    limit: int = 10,
    collection: str = "sentinel-2-l2a",
) -> list:
    """
    Cerca scene Sentinel-2 L2A (già corrette atmosfericamente, pronte per
    NDVI) su un'area e un periodo, filtrando per copertura nuvolosa massima.

    bbox_wgs84: [west, south, east, north] in gradi.
    start_date / end_date: formato "YYYY-MM-DD".
    """
    client = CDSEClient()  # legge CDSE_CLIENT_ID / CDSE_CLIENT_SECRET dall'ambiente
    return client.search(
        bbox=bbox_wgs84,
        start_date=start_date,
        end_date=end_date,
        collection=collection,
        cloud_cover_max=cloud_cover_max,
        limit=limit,
    )


def download_products(products: list, output_dir: str = "./data/raw/sentinel2") -> list[str]:
    """Scarica i prodotti trovati da search_sentinel2(). Attenzione: possono essere ~1GB l'uno."""
    os.makedirs(output_dir, exist_ok=True)
    client = CDSEClient(output_dir=output_dir)
    return client.download_all(products)


def build_ndvi_timeseries_dates(start_year: int, end_year: int, month: int = 6) -> list[tuple[str, str]]:
    """
    Genera una lista di intervalli (start, end) per costruire una serie
    storica NDVI comparabile stagione-su-stagione (es. ogni giugno, per
    evitare che la variazione stagionale "mascheri" la debolezza cronica
    del suolo dietro alla normale fenologia delle colture).
    """
    return [
        (f"{year}-{month:02d}-01", f"{year}-{month:02d}-28")
        for year in range(start_year, end_year + 1)
    ]
