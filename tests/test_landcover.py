from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.domain import AnalysisArea
from src.landcover import CLC_PLUS_CLASSES, compute_land_cover

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

CLC_CRS = "EPSG:3035"
RESOLUTION_M = 10.0
PAD_PIXELS = 2


def _synthetic_clc(area: AnalysisArea, grid_fn: Any) -> bytes:
    """GeoTIFF categorico EPSG:3035 con classi da `grid_fn(rows, cols)`."""
    minx, miny, maxx, maxy = area.projected_geometry(CLC_CRS).bounds
    cols = int((maxx - minx) / RESOLUTION_M) + 2 * PAD_PIXELS
    rows = int((maxy - miny) / RESOLUTION_M) + 2 * PAD_PIXELS
    west = minx - PAD_PIXELS * RESOLUTION_M
    north = maxy + PAD_PIXELS * RESOLUTION_M
    grid = grid_fn(rows, cols).astype(np.uint8)

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="uint8",
            crs=CLC_CRS,
            transform=from_origin(west, north, RESOLUTION_M, RESOLUTION_M),
        ) as dataset:
            dataset.write(grid, 1)
        return memfile.read()


@pytest.fixture
def area() -> AnalysisArea:
    return AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)


def test_land_cover_distribution(area: AnalysisArea) -> None:
    def grid_fn(rows: int, cols: int) -> np.ndarray:
        grid = np.full((rows, cols), 6, dtype=np.uint8)  # prati
        grid[:, : cols // 2] = 7  # meta' ovest: seminativi
        grid[: rows // 4, -cols // 4 :] = 4  # angolo: sempreverdi
        return grid

    result = compute_land_cover(_synthetic_clc(area, grid_fn), area)

    assert result["year"] == 2021
    assert result["resolutionMeters"] == 10
    assert result["dominantClass"] == 7
    classes = {entry["code"]: entry for entry in result["classes"]}
    assert set(classes) <= {4, 6, 7}
    # Seminativi ~50% (bordi tagliati dal poligono a parte)
    assert classes[7]["share"] == pytest.approx(0.5, abs=0.08)
    assert classes[7]["label"] == CLC_PLUS_CLASSES[7]
    # 1 pixel 10m = 0,01 ha
    total_ha = sum(entry["hectares"] for entry in result["classes"])
    assert total_ha == pytest.approx(result["validPixels"] * 0.01, abs=0.05)
    assert total_ha == pytest.approx(
        area.area_hectares(area.local_utm_crs()), rel=0.25
    )


def test_land_cover_single_class(area: AnalysisArea) -> None:
    grid_fn = lambda rows, cols: np.full((rows, cols), 7, dtype=np.uint8)  # noqa: E731

    result = compute_land_cover(_synthetic_clc(area, grid_fn), area)

    assert result["dominantClass"] == 7
    assert len(result["classes"]) == 1
    assert result["classes"][0]["share"] == 1.0


def test_land_cover_without_valid_pixels_raises(area: AnalysisArea) -> None:
    grid_fn = lambda rows, cols: np.zeros((rows, cols), dtype=np.uint8)  # noqa: E731

    with pytest.raises(ValueError, match="pixel validi"):
        compute_land_cover(_synthetic_clc(area, grid_fn), area)


def test_land_cover_excludes_outside_area_and_nodata(area: AnalysisArea) -> None:
    """254 ('Outside area', mare) e 255 ('No data') non contano come pixel validi."""
    def grid_fn(rows: int, cols: int) -> np.ndarray:
        grid = np.full((rows, cols), 7, dtype=np.uint8)
        grid[:, : cols // 2] = 254  # meta' ovest: mare
        grid[: rows // 4, cols // 2 :] = 255  # angolo: no data
        return grid

    result = compute_land_cover(_synthetic_clc(area, grid_fn), area)

    codes = {entry["code"] for entry in result["classes"]}
    assert codes == {7}
    assert result["classes"][0]["share"] == 1.0
    assert result["dominantClass"] == 7
