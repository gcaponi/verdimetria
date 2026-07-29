from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from src.domain import AnalysisArea
from src.ingestion import tinitaly
from src.ingestion.tinitaly import (
    TINITALY_CRS,
    compute_morphometry_tinitaly,
    ensure_tile,
    tile_code_for_point,
    tile_codes_for_area,
)

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

RESOLUTION_M = 10.0


@pytest.fixture
def area() -> AnalysisArea:
    return AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)


def _to_32632(lon: float, lat: float) -> tuple[float, float]:
    return Transformer.from_crs("EPSG:4326", TINITALY_CRS, always_xy=True).transform(lon, lat)


def _write_tile(path: Path, area: AnalysisArea, elevation_fn: Any) -> None:
    minx, miny, maxx, maxy = area.projected_geometry(TINITALY_CRS).bounds
    cols = int((maxx - minx) / RESOLUTION_M) + 4
    rows = int((maxy - miny) / RESOLUTION_M) + 4
    west = minx - 2 * RESOLUTION_M
    north = maxy + 2 * RESOLUTION_M
    xs = west + (np.arange(cols) + 0.5) * RESOLUTION_M
    ys = north - (np.arange(rows) + 0.5) * RESOLUTION_M
    grid_x, grid_y = np.meshgrid(xs, ys)
    z = elevation_fn(grid_x, grid_y).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=TINITALY_CRS,
        transform=from_origin(west, north, RESOLUTION_M, RESOLUTION_M),
    ) as dataset:
        dataset.write(z, 1)


def test_tile_code_matches_real_sicily_tile() -> None:
    # Il tile reale e41005_s10 copre E 1050-1070 km, N 4100-4150 km (EPSG:32632).
    assert tile_code_for_point(1_055_000, 4_120_000) == "e41005"


def test_tile_code_west_prefix() -> None:
    code = tile_code_for_point(800_000, 3_900_000)
    assert code.startswith("w")
    assert code.endswith("80")


def test_tile_codes_for_field_is_single_tile(area: AnalysisArea) -> None:
    codes = tile_codes_for_area(area)
    assert len(codes) == 1
    lon, lat = FIELD_POLYGON["coordinates"][0][0]
    expected = tile_code_for_point(*_to_32632(lon, lat))
    assert codes == [expected]


def test_ensure_tile_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cached = tmp_path / "e41005.tif"
    cached.write_bytes(b"fake")
    spy = Mock(side_effect=AssertionError("non deve scaricare"))
    monkeypatch.setattr(tinitaly.requests, "get", spy)
    assert ensure_tile("e41005", tmp_path) == cached


def test_ensure_tile_missing_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock(status_code=404)
    get_mock = Mock(return_value=response)
    monkeypatch.setattr(tinitaly.requests, "get", get_mock)
    assert ensure_tile("w00000", tmp_path) is None
    url = get_mock.call_args[0][0]
    assert url.endswith("/w00000_s10/w00000_s10.zip")


def test_morphometry_tinitaly_on_ramp(area: AnalysisArea, tmp_path: Path) -> None:
    code = tile_codes_for_area(area)[0]
    # Piano +0,1 m/m verso Est → pendenza 5,71°, discesa a Ovest.
    _write_tile(tmp_path / f"{code}.tif", area, lambda x, y: 100.0 + 0.1 * x)

    terrain = compute_morphometry_tinitaly(area, tmp_path)

    assert terrain["slope"]["mean"] == pytest.approx(5.7, abs=0.3)
    assert terrain["aspectDominant"] == "W"
    assert terrain["resolutionMeters"] == 10
    assert "TINITALY" in terrain["source"]
    assert terrain["validPixels"] > 0


def test_morphometry_tinitaly_without_tiles_raises(area: AnalysisArea, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Nessun tile TINITALY"):
        compute_morphometry_tinitaly(area, tmp_path)
