"""Statistiche zonali land cover CLC+ Backbone 2021 (10 m, 11 classi).

Il raster categorico (EPSG:3035) viene scaricato una-tantum via WEkEO e
servito in locale come GeoTIFF: nessuna chiamata di rete a runtime.
Modulo puro: raster + AnalysisArea -> dict per il contratto FieldAnalysis.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import rasterio
import rasterio.mask
from shapely.geometry import mapping

from src.domain import AnalysisArea

CLC_PLUS_YEAR = 2021
CLC_PLUS_SOURCE = "CLC+ Backbone"
MAX_CLASSES_IN_REPORT = 5

# Legenda ufficiale CLC+ Backbone raster (Product User Manual EEA + file .qml).
# I codici 253/254/255 NON sono classi land cover: 254 = "Outside area"
# (mare/fuori copertura), 255 = "No data" — vanno esclusi dai pixel validi.
CLC_PLUS_CLASSES: dict[int, str] = {
    1: "Suolo sigillato",
    2: "Bosco di aghiformi",
    3: "Bosco di latifoglie decidue",
    4: "Bosco di latifoglie sempreverdi",
    5: "Arbusti e macchia bassa",
    6: "Erbacee permanenti (prati, pascoli)",
    7: "Erbacee periodiche (seminativi)",
    8: "Licheni e muschi",
    9: "Non vegetato o poco vegetato",
    10: "Acqua",
    11: "Neve e ghiaccio",
}

MIN_CLASS_CODE = 1
MAX_CLASS_CODE = 11

HECTARES_PER_SQM = 0.0001


@contextmanager
def _open_raster(source: str | Path | bytes) -> Iterator[rasterio.DatasetReader]:
    if isinstance(source, bytes):
        with rasterio.io.MemoryFile(source) as memfile:
            with memfile.open() as dataset:
                yield dataset
    else:
        with rasterio.open(source) as dataset:
            yield dataset


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def compute_land_cover(source: str | Path | bytes, area: AnalysisArea) -> dict[str, Any]:
    """Distribuzione delle classi CLC+ sul poligono (quote % e ettari)."""
    with _open_raster(source) as dataset:
        dataset_crs = dataset.crs.to_string()
        geometry = [mapping(area.projected_geometry(dataset_crs))]
        masked, transform = rasterio.mask.mask(dataset, geometry, crop=True, nodata=0)
        classes_grid = masked[0]
        pixel_area_ha = abs(transform.a * transform.e) * HECTARES_PER_SQM

    valid = (classes_grid >= MIN_CLASS_CODE) & (classes_grid <= MAX_CLASS_CODE)
    valid_pixels = int(valid.sum())
    if valid_pixels == 0:
        raise ValueError("Il raster CLC+ non contiene pixel validi sul poligono")

    values, counts = np.unique(classes_grid[valid], return_counts=True)
    distribution = sorted(
        zip(values.tolist(), counts.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )

    classes = [
        {
            "code": int(code),
            "label": CLC_PLUS_CLASSES.get(int(code), f"Classe {int(code)}"),
            "share": _round(count / valid_pixels),
            "hectares": _round(count * pixel_area_ha, 2),
        }
        for code, count in distribution[:MAX_CLASSES_IN_REPORT]
    ]

    return {
        "year": CLC_PLUS_YEAR,
        "source": CLC_PLUS_SOURCE,
        "resolutionMeters": int(round(abs(transform.a))),
        "dominantClass": classes[0]["code"],
        "classes": classes,
        "validPixels": valid_pixels,
    }
