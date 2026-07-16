"""
Modulo agricolo — dove il terreno è cronicamente più debole, e in cosa.

A differenza del modulo geologico (statico, un'unica lettura nel tempo), qui
il vantaggio è che i dati CAMBIANO nel tempo: possiamo confrontare una
parcella con se stessa nel tempo e con le parcelle vicine nello stesso
momento, invece di dover indovinare un'anomalia da un'unica istantanea.

Pipeline:
    1. NDVI su più date (da Sentinel-2)          -> vitalità della vegetazione
    2. z-score spaziale per ogni data             -> "quanto più debole della
                                                       media dell'area in quel
                                                       momento"
    3. media dei z-score nel tempo                -> "debolezza cronica"
       (una parcella scarsa solo per un mese non è debolezza strutturale,
       una parcella scarsa in ogni rilievo probabilmente sì)
    4. incrocio con SoilGrids (pH, azoto, carbonio
       organico, tessitura...)                    -> quale proprietà del
                                                       suolo è più bassa nelle
                                                       zone deboli, come primo
                                                       indizio di "sostanza X"
"""

from __future__ import annotations

import numpy as np


def compute_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - RED) / (NIR + RED). Valori tra -1 e 1; vegetazione sana ~0.6-0.9."""
    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)
    return ndvi


def spatial_zscore(grid: np.ndarray) -> np.ndarray:
    """Quanto ogni pixel si discosta (in deviazioni standard) dalla media dell'intera AOI in quella data."""
    valid = ~np.isnan(grid)
    mean = np.nanmean(grid)
    std = np.nanstd(grid)
    z = np.full_like(grid, np.nan)
    z[valid] = (grid[valid] - mean) / (std + 1e-9)
    return z


def chronic_weakness_score(ndvi_timeseries: list[np.ndarray]) -> np.ndarray:
    """
    Prende una lista di grid NDVI (una per data di sorvolo Sentinel-2, stessa
    griglia/shape) e ritorna un unico punteggio di "debolezza cronica" per
    pixel: media degli z-score negativi nel tempo.

    Un punteggio molto negativo = pixel sistematicamente sotto la media
    dell'area in (quasi) tutte le date disponibili -> debolezza strutturale,
    non un evento isolato (es. una nuvola, un ciclo colturale diverso).
    """
    if not ndvi_timeseries:
        raise ValueError("Serve almeno una data NDVI")

    zscores = np.stack([spatial_zscore(g) for g in ndvi_timeseries], axis=0)
    return np.nanmean(zscores, axis=0)


def attribute_limiting_factor(
    weak_mask: np.ndarray,
    soil_properties: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """
    Per i pixel marcati come "deboli" (weak_mask booleana), calcola per ognuno
    quale proprietà del suolo (chiave del dict soil_properties, es. "phh2o",
    "nitrogen", "soc"...) è più anomala rispetto alla media dell'intera AOI.

    Ritorna un dizionario {nome_proprietà: z-score grid}, così puoi vedere,
    pixel per pixel dentro le zone deboli, QUALE variabile spicca di più —
    è la prima ipotesi di "debole in sostanza X o Y" richiesta, da confermare
    poi con un'analisi di laboratorio puntuale prima di agire.
    """
    zscored = {name: spatial_zscore(grid) for name, grid in soil_properties.items()}

    # Per ogni pixel debole, quale proprietà ha lo z-score (in valore assoluto) più estremo
    stacked = np.stack(list(zscored.values()), axis=0)  # (n_proprietà, righe, colonne)
    names = list(zscored.keys())

    abs_stacked = np.abs(stacked)
    abs_stacked_masked = np.where(weak_mask[None, :, :], abs_stacked, np.nan)

    with np.errstate(invalid="ignore"):
        dominant_idx = np.nanargmax(np.nan_to_num(abs_stacked_masked, nan=-np.inf), axis=0)

    dominant_factor = np.full(weak_mask.shape, "", dtype=object)
    rows, cols = np.where(weak_mask)
    for r, c in zip(rows, cols):
        dominant_factor[r, c] = names[dominant_idx[r, c]]

    return {"zscores": zscored, "dominant_factor_grid": dominant_factor}
