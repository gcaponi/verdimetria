"""
Motore generico per lavorare con stack di raster geospaziali come matrici
di feature per il machine learning.

Il pattern qui dentro è una versione modernizzata di quello trovato in diversi
progetti di ricerca sul mineral prospectivity mapping (es. Abdallah-M-Ali/
Mineral-Prospectivity-Mapping-ML): invece delle binding gdal/ogr grezze, usa
rasterio; non richiede etichette (funziona anche per l'anomaly detection
unsupervised); non ha path hardcoded.

Pipeline tipica:
    1. load_stack()          -> carica N raster (anche a risoluzioni diverse)
                                 e li allinea su una griglia comune
    2. to_pixel_matrix()     -> reshape (righe, colonne, bande) -> (pixel, bande)
    3. <addestra un modello> -> scikit-learn, su tutti i pixel o su un subset
                                 etichettato (rasterize_labels, se disponibile)
    4. predictions_to_grid() -> rimette le predizioni nella forma (righe, colonne)
    5. write_raster()        -> salva il risultato come GeoTIFF georeferenziato
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from rasterio.transform import Affine


@dataclass
class RasterStack:
    """Uno stack di raster allineati sulla stessa griglia (stesso transform/crs/shape)."""
    data: np.ndarray          # shape (righe, colonne, bande)
    transform: Affine
    crs: str
    nodata: float | None
    band_names: list[str]

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.data.shape

    def valid_mask(self) -> np.ndarray:
        """Maschera booleana (righe, colonne): True dove NESSUNA banda è nodata/NaN."""
        if self.nodata is not None:
            invalid = np.any(self.data == self.nodata, axis=2)
        else:
            invalid = np.zeros(self.data.shape[:2], dtype=bool)
        invalid |= np.any(np.isnan(self.data), axis=2)
        return ~invalid


def load_stack(
    paths: list[str],
    band_names: list[str] | None = None,
    reference_index: int = 0,
    target_resolution_m: float | None = None,
    resampling: Resampling = Resampling.bilinear,
) -> RasterStack:
    """
    Carica più file raster (ognuno anche multi-banda) e li allinea tutti sulla
    griglia del raster di riferimento (default: il primo della lista).

    Ogni raster con CRS/risoluzione/estensione diversi viene riproiettato al
    volo sulla griglia comune. Questo è ciò che ti serve quando incroci, ad
    esempio, un DEM Copernicus a 30m con una banda Sentinel-2 a 10m e un layer
    SoilGrids a 250m: escono tutti allineati pixel-per-pixel.
    """
    if not paths:
        raise ValueError("Serve almeno un percorso raster")

    with rasterio.open(paths[reference_index]) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_width, ref_height = ref.width, ref.height

        if target_resolution_m is not None:
            # Ricalcola una griglia alla risoluzione desiderata, stesso CRS/estensione
            ref_transform, ref_width, ref_height = calculate_default_transform(
                ref_crs, ref_crs, ref.width, ref.height, *ref.bounds,
                resolution=target_resolution_m,
            )

    bands: list[np.ndarray] = []
    names: list[str] = []
    nodata_value = None

    for p in paths:
        with rasterio.open(p) as src:
            if nodata_value is None:
                nodata_value = src.nodata
            for b in range(1, src.count + 1):
                dest = np.full((ref_height, ref_width), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(src, b),
                    destination=dest,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=ref_transform,
                    dst_crs=ref_crs,
                    resampling=resampling,
                    dst_nodata=np.nan,
                )
                bands.append(dest)
                names.append(f"{p.split('/')[-1]}_b{b}")

    stacked = np.dstack(bands)

    if band_names is not None:
        if len(band_names) != stacked.shape[2]:
            raise ValueError(
                f"band_names ha {len(band_names)} elementi ma lo stack ha {stacked.shape[2]} bande"
            )
        names = band_names

    return RasterStack(
        data=stacked,
        transform=ref_transform,
        crs=str(ref_crs),
        nodata=nodata_value,
        band_names=names,
    )


def to_pixel_matrix(stack: RasterStack) -> tuple[np.ndarray, np.ndarray]:
    """
    Trasforma lo stack (righe, colonne, bande) in una matrice (pixel_validi, bande),
    pronta per scikit-learn. Ritorna anche la maschera dei pixel validi, necessaria
    per rimettere le predizioni al loro posto con predictions_to_grid().
    """
    mask = stack.valid_mask()
    matrix = stack.data[mask]  # (n_pixel_validi, n_bande)
    return matrix, mask


def predictions_to_grid(predictions: np.ndarray, mask: np.ndarray, fill_value: float = np.nan) -> np.ndarray:
    """Rimette un array 1D di predizioni (una per pixel valido) nella forma 2D originale."""
    grid = np.full(mask.shape, fill_value, dtype=np.float32)
    grid[mask] = predictions
    return grid


def write_raster(path: str, grid: np.ndarray, transform: Affine, crs: str, nodata: float = np.nan) -> None:
    """Scrive un array 2D come GeoTIFF a singola banda, georeferenziato."""
    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=grid.shape[0],
        width=grid.shape[1],
        count=1,
        dtype=grid.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(grid, 1)


def rasterize_labels(vector_path: str, stack: RasterStack, value_field: str) -> np.ndarray:
    """
    OPZIONALE — solo se hai punti/poligoni di verità nota (es. analisi di laboratorio
    del suolo in punti specifici, o depositi noti). Rasterizza il vettoriale sulla
    stessa griglia dello stack, per costruire un training set supervisionato.

    Se non hai dati etichettati (il caso più comune per Ragusa in ambito geologico),
    salta questa funzione e usa direttamente i modelli unsupervised in geo_module/.
    """
    import geopandas as gpd
    from rasterio.features import rasterize

    gdf = gpd.read_file(vector_path)
    if gdf.crs is None:
        raise ValueError("Il file vettoriale non ha un CRS definito")
    gdf = gdf.to_crs(stack.crs)

    shapes = [(geom, value) for geom, value in zip(gdf.geometry, gdf[value_field])]
    labels = rasterize(
        shapes,
        out_shape=stack.data.shape[:2],
        transform=stack.transform,
        fill=np.nan,
        dtype=np.float32,
    )
    return labels
