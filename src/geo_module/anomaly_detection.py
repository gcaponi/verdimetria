"""
Modulo geologico — rilevamento anomalie multivariate SENZA etichette.

A differenza dei repository di prospectivity mapping "classici" (KoBold,
Abdallah-M-Ali, mheriyanto...), qui NON abbiamo depositi noti su cui
addestrare un classificatore supervisionato: per il territorio di Ragusa non
esiste un dataset pubblico di "qui c'è / qui non c'è" da usare come target.

L'approccio realistico, discusso anche in chat, è quindi unsupervised:
troviamo le combinazioni di feature (litologia, morfologia, indici spettrali,
prossimità a geositi noti...) che sono statisticamente anomale rispetto al
resto del territorio. Questo NON prova che lì ci sia qualcosa: è un'ipotesi
di lettura da validare sempre con un geologo, non una scoperta.
"""

from __future__ import annotations

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.core.raster_stack import RasterStack, to_pixel_matrix, predictions_to_grid


def compute_anomaly_score(
    stack: RasterStack,
    contamination: float = 0.05,
    random_state: int = 42,
) -> np.ndarray:
    """
    Calcola un punteggio di anomalia (0 = normale, 1 = anomalo) per ogni pixel,
    combinando tutte le bande dello stack (litologia, morfologia, indici...).

    contamination: proporzione attesa di pixel "anomali" nell'area totale.
    5% è un default ragionevole per partire; alzalo/abbassalo in base a
    quanti punti vuoi che emergano per un'ispezione manuale successiva.
    """
    matrix, mask = to_pixel_matrix(stack)

    scaler = StandardScaler()
    matrix_scaled = scaler.fit_transform(matrix)

    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(matrix_scaled)

    # decision_function: più alto = più "normale". Invertiamo e normalizziamo
    # in [0, 1] così "1" = pixel più anomalo, più intuitivo da visualizzare.
    raw_scores = -model.decision_function(matrix_scaled)
    normalized = (raw_scores - raw_scores.min()) / (raw_scores.max() - raw_scores.min() + 1e-9)

    return predictions_to_grid(normalized, mask)


def compute_pca_projection(stack: RasterStack, n_components: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """
    Riduce lo stack multi-banda a n_components (default 3, per una visualizzazione
    RGB) via PCA. Utile per "vedere a occhio" dove il territorio si discosta dai
    pattern dominanti, prima ancora di guardare il punteggio di anomalia.

    Ritorna (componenti come griglia (righe, colonne, n_components), varianza spiegata).
    """
    matrix, mask = to_pixel_matrix(stack)
    scaler = StandardScaler()
    matrix_scaled = scaler.fit_transform(matrix)

    pca = PCA(n_components=n_components, random_state=42)
    components = pca.fit_transform(matrix_scaled)

    grids = [predictions_to_grid(components[:, i], mask) for i in range(n_components)]
    return np.dstack(grids), pca.explained_variance_ratio_


def top_anomaly_locations(
    anomaly_grid: np.ndarray,
    transform,
    crs: str,
    top_n: int = 20,
) -> list[dict]:
    """
    Estrae le coordinate (in CRS geografico, lon/lat) dei top_n pixel più anomali,
    così puoi caricarle su una mappa o portarle sul campo per un controllo visivo.
    """
    import rasterio.warp
    from pyproj import Transformer

    flat_idx = np.argsort(anomaly_grid.flatten())[::-1]
    flat_idx = flat_idx[~np.isnan(anomaly_grid.flatten()[flat_idx])][:top_n]

    rows, cols = np.unravel_index(flat_idx, anomaly_grid.shape)
    xs, ys = rasterio.transform.xy(transform, rows, cols)

    to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lons, lats = to_wgs84.transform(xs, ys)

    return [
        {"rank": i + 1, "lon": float(lon), "lat": float(lat), "score": float(anomaly_grid[r, c])}
        for i, (lon, lat, r, c) in enumerate(zip(lons, lats, rows, cols))
    ]
