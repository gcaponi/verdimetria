"""TINITALY 1.1 (INGV, CC BY 4.0) — DEM 10 m Italia con download lazy per tile.

Griglia nominale 50x50 km in EPSG:32632, tile ritagliati su coste/confini.
Il tile si scarica una-tantum e resta in cache su disco: nessuna dipendenza
di rete a runtime dopo il primo uso, nessun raster nazionale da mantenere.

Pattern del codice tile (verificato su bounds reali + Accompanying Notes):
  {e|w}{N}{EE}  ->  e41005 = N 4100 km, E 1050 km (Sicilia sud-orientale)
- prefisso 'e' se E_left >= 1000 km, 'w' altrimenti
- N = northing in unita' di 10 km (4100 km -> "410", 4250 km -> "425")
- EE = indice est su 2 cifre: (E_left_km - 1000) / 10 per 'e', E_left_km / 10 per 'w'
"""

from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import requests
from affine import Affine
from rasterio.merge import merge

from src.domain import AnalysisArea
from src.terrain import compute_morphometry_from_array

TINITALY_CRS = "EPSG:32632"
TINITALY_SOURCE = "TINITALY 1.1 (INGV, CC BY 4.0)"
TINITALY_BASE_URL = "https://tinitaly.pi.ingv.it/data_1.1"
TILE_METERS = 50_000
REQUEST_TIMEOUT = (30, 300)


def _n_code(northing_m: float) -> str:
    """Northing in unita' di 10 km: 4100 km -> "410", 3900 km -> "390"."""
    return str(int(northing_m // 10_000))


def tile_code_for_point(easting_m: float, northing_m: float) -> str:
    """Codice tile TINITALY 1.1 per un punto in EPSG:32632."""
    e_left = math.floor(easting_m / TILE_METERS) * TILE_METERS
    n_bottom = math.floor(northing_m / TILE_METERS) * TILE_METERS
    if e_left >= 1_000_000:
        prefix = "e"
        e_idx = int((e_left - 1_000_000) // 10_000)
    else:
        prefix = "w"
        e_idx = int(e_left // 10_000)
    return f"{prefix}{_n_code(n_bottom)}{e_idx:02d}"


def tile_codes_for_area(area: AnalysisArea) -> list[str]:
    """Tutti i tile che il bounding box del poligono interseca (1-4 tipici)."""
    minx, miny, maxx, maxy = area.projected_geometry(TINITALY_CRS).bounds
    codes = set()
    eastings = range(
        math.floor(minx / TILE_METERS) * TILE_METERS,
        math.floor(maxx / TILE_METERS) * TILE_METERS + 1,
        TILE_METERS,
    )
    northings = range(
        math.floor(miny / TILE_METERS) * TILE_METERS,
        math.floor(maxy / TILE_METERS) * TILE_METERS + 1,
        TILE_METERS,
    )
    for easting in eastings:
        for northing in northings:
            codes.add(tile_code_for_point(easting + 1, northing + 1))
    return sorted(codes)


def _extract_tif(zip_bytes: bytes, code: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith(".tif") and code in name
        ]
        if not candidates:
            raise ValueError(f"Tile {code}: nessun .tif atteso nello zip")
        return archive.read(candidates[0])


def ensure_tile(code: str, cache_dir: Path) -> Path | None:
    """Path del tif in cache; None se il tile non esiste (mare/fuori griglia)."""
    cached = cache_dir / f"{code}.tif"
    if cached.exists():
        return cached
    url = f"{TINITALY_BASE_URL}/{code}_s10/{code}_s10.zip"
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(_extract_tif(response.content, code))
    return cached


def fetch_dem(area: AnalysisArea, cache_dir: Path) -> tuple[np.ndarray, Affine]:
    """Array quota (float64) + transform per l'area, unendo i tile necessari."""
    paths = []
    for code in tile_codes_for_area(area):
        path = ensure_tile(code, cache_dir)
        if path is not None:
            paths.append(path)
    if not paths:
        raise ValueError("Nessun tile TINITALY disponibile per l'area")

    projected = area.projected_geometry(TINITALY_CRS)
    datasets = [rasterio.open(path) for path in paths]
    try:
        data, transform = merge(datasets, bounds=projected.bounds, nodata=math.nan)
    finally:
        for dataset in datasets:
            dataset.close()
    return data[0].astype(np.float64), transform


def compute_morphometry_tinitaly(
    area: AnalysisArea,
    cache_dir: Path,
) -> dict[str, Any]:
    """Morfometria 10 m da TINITALY sul poligono (stesso contratto di terrain)."""
    elevation, transform = fetch_dem(area, cache_dir)
    return compute_morphometry_from_array(
        elevation,
        transform,
        area.projected_geometry(TINITALY_CRS),
        TINITALY_CRS,
        TINITALY_SOURCE,
    )
