"""Feature morfometriche da DEM: quota, pendenza, esposizione dominante.

Modulo puro: GeoTIFF bytes + AnalysisArea -> dict pronto per il contratto
FieldAnalysis. Nessuna chiamata di rete.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import rasterio
import rasterio.mask
from scipy.ndimage import binary_erosion
from shapely.geometry import mapping

from src.domain import AnalysisArea

ASPECT_SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
FLAT_SLOPE_THRESHOLD_DEG = 2.0
FLAT_LABEL = "Pianeggiante"


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _aspect_label(degrees: float) -> str:
    index = int(((degrees + 22.5) % 360) // 45)
    return ASPECT_SECTORS[index]


def compute_morphometry(tiff_bytes: bytes, area: AnalysisArea) -> dict[str, Any]:
    """Statistiche morfometriche sul poligono dal GeoTIFF DEM (FLOAT32, m)."""
    with rasterio.io.MemoryFile(tiff_bytes) as memfile:
        with memfile.open() as dataset:
            dataset_crs = dataset.crs.to_string()
            geometry = [mapping(area.projected_geometry(dataset_crs))]
            masked, transform = rasterio.mask.mask(dataset, geometry, crop=True, nodata=np.nan)
            elevation = masked[0].astype(np.float64)
            resolution_m = float(abs(transform.a))

    valid = ~np.isnan(elevation)
    valid_pixels = int(valid.sum())
    if valid_pixels == 0:
        raise ValueError("Il DEM non contiene pixel validi sul poligono")

    values = elevation[valid]
    # Il gradiente richiede una griglia senza NaN: riempiamo con la media
    # (artefatto solo ai bordi), poi le statistiche usano solo i pixel validi.
    filled = np.where(valid, elevation, float(values.mean()))
    grad_y, grad_x = np.gradient(filled, resolution_m, resolution_m)
    slope_deg = np.degrees(np.arctan(np.hypot(grad_x, grad_y)))

    # Pendenza/esposizione affidabili solo dove l'intorno 3x3 e' tutto dentro
    # il poligono: ai bordi il fill mediato falserebbe il gradiente. Su campi
    # minuscoli (< 3 pixel) si ripiega su tutti i pixel validi.
    interior = binary_erosion(valid, structure=np.ones((3, 3)), border_value=0)
    gradient_mask = interior if int(interior.sum()) > 0 else valid
    valid_slope = slope_deg[gradient_mask]
    steep = gradient_mask & (slope_deg >= FLAT_SLOPE_THRESHOLD_DEG)
    if steep.sum() == 0:
        aspect_dominant: str | None = FLAT_LABEL
    else:
        # Aspetto = direzione di discesa (downslope), gradi da Nord in senso orario.
        # grad_x = dz/dEst; grad_y = dz/driga (le righe aumentano verso Sud),
        # quindi la discesa e' (-grad_x, +grad_y) in componenti (Est, Nord).
        aspect_deg = (np.degrees(np.arctan2(-grad_x, grad_y)) + 360.0) % 360.0
        counts = np.zeros(len(ASPECT_SECTORS), dtype=np.int64)
        labels = np.char.array([_aspect_label(d) for d in aspect_deg[steep].tolist()])
        for i, sector in enumerate(ASPECT_SECTORS):
            counts[i] = int((labels == sector).sum())
        aspect_dominant = ASPECT_SECTORS[int(counts.argmax())]

    return {
        "elevation": {
            "min": _round(values.min(), 1),
            "max": _round(values.max(), 1),
            "mean": _round(values.mean(), 1),
        },
        "slope": {
            "mean": _round(valid_slope.mean(), 1),
            "max": _round(valid_slope.max(), 1),
        },
        "aspectDominant": aspect_dominant,
        "resolutionMeters": int(round(resolution_m)),
        "validPixels": valid_pixels,
    }
