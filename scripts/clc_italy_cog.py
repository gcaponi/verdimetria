"""Clip del raster CLC+ Backbone 2021 sull'estensione Italia e conversione in COG.

Uso: .venv/bin/python scripts/clc_italy_cog.py <zip_o_tif_input> <output_tif>
Il raster sorgente e' EPSG:3035, uint8, 11 classi (vedi src/landcover.py).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import WindowError
from rasterio.windows import Window, from_bounds

# Estensione Italia (isole incluse) in lon/lat, convertita in EPSG:3035 a runtime.
ITALY_BOUNDS_LONLAT = (6.6, 35.4, 18.6, 47.2)


def extract_tif(zip_path: Path, work_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as archive:
        tifs = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
        if not tifs:
            raise SystemExit("Nessun .tif nello zip")
        name = max(tifs, key=lambda n: archive.getinfo(n).file_size)
        archive.extract(name, work_dir)
        return work_dir / name


def clip_to_italy(source: Path, output: Path) -> None:
    from pyproj import Transformer

    with rasterio.open(source) as dataset:
        transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        minx, miny = transformer.transform(ITALY_BOUNDS_LONLAT[0], ITALY_BOUNDS_LONLAT[1])
        maxx, maxy = transformer.transform(ITALY_BOUNDS_LONLAT[2], ITALY_BOUNDS_LONLAT[3])
        window = from_bounds(minx, miny, maxx, maxy, dataset.transform).round_offsets().round_lengths()

        profile = dataset.profile.copy()
        profile.update(
            driver="COG",
            height=int(window.height),
            width=int(window.width),
            transform=dataset.window_transform(window),
            compress="deflate",
            blocksize=512,
            num_threads="ALL_CPUS",
        )
        with rasterio.open(output, "w", **profile) as dest:
            for _, tile_window in dataset.block_windows(1):
                try:
                    target = tile_window.intersection(window)
                except WindowError:
                    continue  # blocco fuori dall'estensione Italia
                data = dataset.read(1, window=target)
                dest_window = Window(
                    target.col_off - window.col_off,
                    target.row_off - window.row_off,
                    target.width,
                    target.height,
                )
                dest.write(data, 1, window=dest_window)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source = input_path
    if input_path.suffix.lower() == ".zip":
        print("Estrazione dallo zip...")
        source = extract_tif(input_path, input_path.parent)

    print(f"Clip Italia + COG: {source} -> {output_path}")
    clip_to_italy(source, output_path)

    with rasterio.open(output_path) as dataset:
        values, counts = np.unique(dataset.read(1), return_counts=True)
        print("dimensioni:", dataset.width, "x", dataset.height, "| crs:", dataset.crs)
        print("classi presenti:", dict(zip(values.tolist(), counts.tolist())))


if __name__ == "__main__":
    main()
