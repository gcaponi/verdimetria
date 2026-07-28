from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.domain import AnalysisArea
from src.ingestion.dem_api import DEM_EVALSCRIPT, build_dem_request
from src.terrain import compute_morphometry

FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.61, 36.92],
        [14.61, 36.93],
        [14.60, 36.93],
        [14.60, 36.92],
    ]],
}

RESOLUTION_M = 30.0
PAD_PIXELS = 2


def _synthetic_dem(
    area: AnalysisArea,
    elevation_fn: Any,
) -> bytes:
    """GeoTIFF FLOAT32 nel CRS metrico dell'area, quota da `elevation_fn(x, y)`."""
    crs = area.local_utm_crs()
    minx, miny, maxx, maxy = area.projected_geometry(crs).bounds
    cols = int((maxx - minx) / RESOLUTION_M) + 2 * PAD_PIXELS
    rows = int((maxy - miny) / RESOLUTION_M) + 2 * PAD_PIXELS
    west = minx - PAD_PIXELS * RESOLUTION_M
    north = maxy + PAD_PIXELS * RESOLUTION_M
    xs = west + (np.arange(cols) + 0.5) * RESOLUTION_M
    ys = north - (np.arange(rows) + 0.5) * RESOLUTION_M
    grid_x, grid_y = np.meshgrid(xs, ys)
    z = elevation_fn(grid_x, grid_y).astype(np.float32)

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="float32",
            crs=crs,
            transform=from_origin(west, north, RESOLUTION_M, RESOLUTION_M),
        ) as dataset:
            dataset.write(z, 1)
        return memfile.read()


@pytest.fixture
def area() -> AnalysisArea:
    return AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)


def test_build_dem_request_uses_dem_collection(area: AnalysisArea) -> None:
    request = build_dem_request(area)

    data = request["input"]["data"][0]
    assert data["type"] == "dem"
    assert "DEM" in DEM_EVALSCRIPT
    output = request["output"]
    # Risoluzione 30 m nativa: il raster e' ~4 volte piu' piccolo che a 10 m.
    request_10m_area = area.raster_dimensions(10, area.local_utm_crs(), 25_000_000)
    assert output["width"] <= request_10m_area.width // 2
    assert output["height"] <= request_10m_area.height // 2
    time_range = data["dataFilter"]["timeRange"]
    assert time_range["from"].startswith("2010-01-01")


def test_morphometry_on_uniform_eastward_ramp(area: AnalysisArea) -> None:
    # Piano inclinato: +0,1 m di quota per metro verso Est → pendenza 5,71°,
    # discesa verso Ovest.
    dem = _synthetic_dem(area, lambda x, y: 100.0 + 0.1 * x)

    terrain = compute_morphometry(dem, area)

    assert terrain["slope"]["mean"] == pytest.approx(5.7, abs=0.2)
    assert terrain["slope"]["max"] == pytest.approx(5.7, abs=0.3)
    assert terrain["aspectDominant"] == "W"
    assert terrain["resolutionMeters"] == 30
    assert terrain["validPixels"] > 0
    assert terrain["elevation"]["min"] < terrain["elevation"]["mean"] < terrain["elevation"]["max"]


def test_morphometry_on_flat_terrain(area: AnalysisArea) -> None:
    dem = _synthetic_dem(area, lambda x, y: np.full_like(x, 120.0))

    terrain = compute_morphometry(dem, area)

    assert terrain["slope"]["mean"] == pytest.approx(0.0, abs=0.1)
    assert terrain["aspectDominant"] == "Pianeggiante"
    assert terrain["elevation"]["min"] == terrain["elevation"]["max"] == 120.0


def test_morphometry_without_valid_pixels_raises(area: AnalysisArea) -> None:
    dem = _synthetic_dem(area, lambda x, y: np.full_like(x, np.nan))

    with pytest.raises(ValueError, match="pixel validi"):
        compute_morphometry(dem, area)
