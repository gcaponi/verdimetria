"""
Demo end-to-end con dati SINTETICI (non reali) georeferenziati sull'area di
Ragusa, per dimostrare che l'intera pipeline (core + geo_module + agro_module
+ viz) funziona prima di collegare le fonti dati vere — che richiedono
credenziali/registrazioni (CDSE) e reti non raggiungibili da questo sandbox
di sviluppo.

Esegui con:
    python -m demo.run_synthetic_demo

Cosa genera:
    outputs/geo_anomaly_score.tif       - punteggio di anomalia geologica
    outputs/agro_weakness_score.tif     - punteggio di debolezza cronica del suolo
    outputs/ragusa_map.html             - mappa interattiva con entrambi i layer
"""

from __future__ import annotations

import os

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from src.config import RAGUSA_AOI, WORKING_CRS, OUTPUTS_DIR
from src.core.raster_stack import load_stack, write_raster
from src.geo_module.anomaly_detection import compute_anomaly_score, top_anomaly_locations
from src.agro_module.soil_weakness import chronic_weakness_score, attribute_limiting_factor, spatial_zscore


RNG = np.random.default_rng(42)
GRID_SIZE = 150  # 150x150 pixel: piccolo apposta per far girare il demo in pochi secondi


def _synthetic_transform():
    """Transform georeferenziato reale sull'AOI di Ragusa, in WGS84."""
    return from_bounds(
        RAGUSA_AOI.west, RAGUSA_AOI.south, RAGUSA_AOI.east, RAGUSA_AOI.north,
        GRID_SIZE, GRID_SIZE,
    )


def _make_synthetic_raster(path: str, n_bands: int, seed_offset: int = 0, add_hotspot: bool = False) -> None:
    """Crea un GeoTIFF sintetico multi-banda con un po' di struttura spaziale (non solo rumore puro)."""
    rng = np.random.default_rng(42 + seed_offset)
    transform = _synthetic_transform()

    xx, yy = np.meshgrid(np.linspace(0, 1, GRID_SIZE), np.linspace(0, 1, GRID_SIZE))
    bands = []
    for b in range(n_bands):
        base = np.sin(xx * (b + 2) * np.pi) * np.cos(yy * (b + 3) * np.pi)
        noise = rng.normal(0, 0.3, size=(GRID_SIZE, GRID_SIZE))
        band = base + noise
        if add_hotspot:
            # Inseriamo deliberatamente un paio di "anomalie" note, per verificare
            # che la pipeline le recuperi davvero (sanity check, non è un dato reale)
            band[20:28, 100:108] += 3.0
            band[110:118, 30:38] -= 3.0
        bands.append(band.astype(np.float32))

    with rasterio.open(
        path, "w", driver="GTiff",
        height=GRID_SIZE, width=GRID_SIZE, count=n_bands,
        dtype=np.float32, crs="EPSG:4326", transform=transform, nodata=np.nan,
    ) as dst:
        for i, band in enumerate(bands, start=1):
            dst.write(band, i)


def run_geo_module_demo(raw_dir: str) -> np.ndarray:
    print("\n=== MODULO GEOLOGICO (unsupervised anomaly detection) ===")

    litologia_path = f"{raw_dir}/litologia_sintetica.tif"
    morfologia_path = f"{raw_dir}/morfologia_sintetica.tif"
    spettrale_path = f"{raw_dir}/indici_spettrali_sintetici.tif"

    _make_synthetic_raster(litologia_path, n_bands=2, seed_offset=1, add_hotspot=True)
    _make_synthetic_raster(morfologia_path, n_bands=2, seed_offset=2, add_hotspot=True)
    _make_synthetic_raster(spettrale_path, n_bands=3, seed_offset=3, add_hotspot=True)

    stack = load_stack(
        [litologia_path, morfologia_path, spettrale_path],
        band_names=["litologia_1", "litologia_2", "pendenza", "curvatura",
                    "indice_1", "indice_2", "indice_3"],
    )
    print(f"Stack caricato: {stack.shape} (righe, colonne, bande)")

    anomaly_grid = compute_anomaly_score(stack, contamination=0.05)
    print(f"Punteggio di anomalia calcolato. Range: [{np.nanmin(anomaly_grid):.3f}, {np.nanmax(anomaly_grid):.3f}]")

    locations = top_anomaly_locations(anomaly_grid, stack.transform, stack.crs, top_n=5)
    print("Top 5 zone più anomale (da validare sempre con un geologo, non sono 'scoperte'):")
    for loc in locations:
        print(f"  #{loc['rank']}: lon={loc['lon']:.4f}, lat={loc['lat']:.4f}, score={loc['score']:.3f}")

    write_raster(f"{OUTPUTS_DIR}/geo_anomaly_score.tif", anomaly_grid, stack.transform, stack.crs)
    print(f"Salvato: {OUTPUTS_DIR}/geo_anomaly_score.tif")

    return anomaly_grid


def run_agro_module_demo(raw_dir: str) -> tuple[np.ndarray, dict]:
    print("\n=== MODULO AGRICOLO (debolezza cronica del suolo) ===")

    # Simuliamo 3 rilievi NDVI (es. giugno di 3 anni diversi)
    ndvi_dates = []
    for i in range(3):
        rng = np.random.default_rng(100 + i)
        base = rng.normal(0.7, 0.1, size=(GRID_SIZE, GRID_SIZE))
        base[60:75, 60:75] -= 0.35  # zona debole "vera" nel dato sintetico, coerente su tutte le date
        ndvi_dates.append(np.clip(base, -1, 1).astype(np.float32))

    weakness = chronic_weakness_score(ndvi_dates)
    print(f"Punteggio di debolezza cronica calcolato. Range: [{np.nanmin(weakness):.3f}, {np.nanmax(weakness):.3f}]")

    weak_mask = weakness < -1.0  # soglia: più di 1 deviazione standard sotto la media, in modo persistente
    n_weak = int(weak_mask.sum())
    print(f"Pixel classificati come 'debolezza cronica': {n_weak} su {GRID_SIZE * GRID_SIZE}")

    # Proprietà del suolo sintetiche (in un progetto reale: output di soilgrids_client.py)
    soil_properties = {}
    for name, seed in [("phh2o", 200), ("nitrogen", 201), ("soc", 202), ("clay", 203)]:
        rng = np.random.default_rng(seed)
        grid = rng.normal(0, 1, size=(GRID_SIZE, GRID_SIZE)).astype(np.float32)
        soil_properties[name] = grid

    # Rendiamo l'azoto deliberatamente basso nella stessa zona debole, per
    # verificare che attribute_limiting_factor() lo recuperi correttamente
    soil_properties["nitrogen"][60:75, 60:75] -= 2.5

    result = attribute_limiting_factor(weak_mask, soil_properties)
    dominant = result["dominant_factor_grid"]
    unique, counts = np.unique(dominant[weak_mask], return_counts=True)
    print("Fattore limitante dominante nelle zone deboli (conteggio pixel):")
    for factor, count in sorted(zip(unique, counts), key=lambda x: -x[1]):
        if factor:
            print(f"  {factor}: {count} pixel")

    transform = _synthetic_transform()
    write_raster(f"{OUTPUTS_DIR}/agro_weakness_score.tif", weakness, transform, "EPSG:4326")
    print(f"Salvato: {OUTPUTS_DIR}/agro_weakness_score.tif")

    return weakness, result


def export_map(anomaly_grid: np.ndarray, weakness_grid: np.ndarray) -> None:
    import folium
    from folium.raster_layers import ImageOverlay
    import matplotlib as mpl

    center_lat = (RAGUSA_AOI.north + RAGUSA_AOI.south) / 2
    center_lon = (RAGUSA_AOI.east + RAGUSA_AOI.west) / 2
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

    bounds = [[RAGUSA_AOI.south, RAGUSA_AOI.west], [RAGUSA_AOI.north, RAGUSA_AOI.east]]

    def to_rgba(grid, cmap_name):
        normed = (grid - np.nanmin(grid)) / (np.nanmax(grid) - np.nanmin(grid) + 1e-9)
        normed = np.nan_to_num(normed, nan=0.0)
        rgba = mpl.colormaps[cmap_name](normed)
        rgba[np.isnan(grid)] = [0, 0, 0, 0]
        return rgba

    ImageOverlay(
        image=to_rgba(anomaly_grid, "inferno"), bounds=bounds,
        name="Anomalia geologica", opacity=0.6,
    ).add_to(fmap)

    ImageOverlay(
        image=to_rgba(-weakness_grid, "RdYlGn_r"), bounds=bounds,
        name="Debolezza cronica suolo", opacity=0.6,
    ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    output_path = f"{OUTPUTS_DIR}/ragusa_map.html"
    fmap.save(output_path)
    print(f"\nMappa interattiva salvata: {output_path}")


def main():
    raw_dir = "data/raw"
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    print("DEMO SINTETICA — Ragusa Geo-Intelligence")
    print(f"AOI: {RAGUSA_AOI.name} bbox={RAGUSA_AOI.as_bbox()}")
    print("NOTA: tutti i dati usati qui sono generati casualmente, servono solo a")
    print("dimostrare che la pipeline gira correttamente end-to-end.\n")

    anomaly_grid = run_geo_module_demo(raw_dir)
    weakness_grid, _ = run_agro_module_demo(raw_dir)
    export_map(anomaly_grid, weakness_grid)

    print("\n=== DEMO COMPLETATA ===")
    print("Prossimo passo reale: sostituisci i file in data/raw/ con dati veri")
    print("(vedi src/ingestion/) e ripeti la stessa pipeline sui tuoi dati.")


if __name__ == "__main__":
    main()
