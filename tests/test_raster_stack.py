"""Test di base sul motore core. Esegui con: pytest tests/"""

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from src.core.raster_stack import load_stack, to_pixel_matrix, predictions_to_grid, write_raster


def _write_test_raster(path, n_bands=2, size=10):
    transform = from_bounds(14.0, 36.0, 15.0, 37.0, size, size)
    data = np.random.default_rng(0).normal(size=(n_bands, size, size)).astype(np.float32)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=n_bands,
        dtype=np.float32, crs="EPSG:4326", transform=transform, nodata=np.nan,
    ) as dst:
        for i in range(n_bands):
            dst.write(data[i], i + 1)
    return data


def test_load_stack_shape(tmp_path):
    path = str(tmp_path / "test.tif")
    _write_test_raster(path, n_bands=3, size=10)

    stack = load_stack([path])
    assert stack.data.shape == (10, 10, 3)
    assert stack.crs is not None


def test_pixel_matrix_roundtrip(tmp_path):
    path = str(tmp_path / "test.tif")
    _write_test_raster(path, n_bands=2, size=8)

    stack = load_stack([path])
    matrix, mask = to_pixel_matrix(stack)

    # nessun nodata iniettato -> tutti i pixel dovrebbero essere validi
    assert mask.sum() == 8 * 8
    assert matrix.shape == (64, 2)

    # roundtrip: predizioni fittizie devono tornare alla shape originale
    fake_predictions = np.arange(matrix.shape[0])
    grid = predictions_to_grid(fake_predictions, mask)
    assert grid.shape == (8, 8)


def test_write_raster_roundtrip(tmp_path):
    out_path = str(tmp_path / "out.tif")
    transform = from_bounds(14.0, 36.0, 15.0, 37.0, 5, 5)
    grid = np.ones((5, 5), dtype=np.float32) * 42.0

    write_raster(out_path, grid, transform, "EPSG:4326")

    with rasterio.open(out_path) as src:
        read_back = src.read(1)
    assert np.allclose(read_back, 42.0)


def test_multi_source_stack_aligns_shapes(tmp_path):
    """Due raster con lo stesso transform ma bande diverse devono impilarsi senza errori."""
    path_a = str(tmp_path / "a.tif")
    path_b = str(tmp_path / "b.tif")
    _write_test_raster(path_a, n_bands=1, size=6)
    _write_test_raster(path_b, n_bands=2, size=6)

    stack = load_stack([path_a, path_b])
    assert stack.data.shape == (6, 6, 3)  # 1 banda + 2 bande = 3 totali
