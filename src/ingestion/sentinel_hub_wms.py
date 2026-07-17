"""
Client WMS per la Configuration Instance "verdimetria" su Sentinel Hub
(Copernicus Data Space Ecosystem).

A differenza di sentinel2_cdse.py (che cerca/scarica scene grezze via
STAC+OAuth), qui chiediamo direttamente un layer GIA' PROCESSATO — es. NDVI,
Agricoltura, Geologia — per un'area, senza scaricare le bande grezze. E' la
via più diretta per il modulo agricolo, dato che il "Full WMS template" li
ha già pronti (li hai visti nello screenshot della tua configurazione).

⚠️ ATTENZIONE — leggi prima di fidarti dei numeri:
I layer come NDVI/EVI/SAVI/Agriculture nel template sono storicamente pensati
per la VISUALIZZAZIONE su mappa (World: restituiscono colori RGB su una scala
cromatica), non necessariamente il valore numerico grezzo dell'indice.
Se apri il layer "NDVI" nella tua configurazione (icona matita) e vedi un
evalscript che ritorna `imgVals = [r,g,b]` in base a soglie di "val", quello
è un layer di VISUALIZZAZIONE: utile per vedere la mappa, MA I VALORI CHE
SCARICHI SONO COLORI, non NDVI reale, e il nostro agro_module/soil_weakness.py
li interpreterebbe in modo sbagliato.

Per numeri reali da usare nella pipeline, hai due strade:
  1. Modifica l'evalscript del layer NDVI (pulsante matita) perché ritorni
     `[ndvi]` come singola banda float, con output `sampleType: "FLOAT32"`
  2. Oppure crea un nuovo layer con l'evalscript "raw" fornito qui sotto
     (RAW_NDVI_EVALSCRIPT) e usalo con SentinelHubRequest anzichè con WMS.

Questo modulo scarica quello che il layer ritorna, qualunque esso sia:
la responsabilità di verificare se è raw o visualizzato è tua, alla prima
prova (guarda l'istogramma dei valori: se sono tutti tra 0-255 su 3 bande,
è visualizzazione; se è una singola banda con valori tra -1 e 1, è raw).
"""

from __future__ import annotations

import requests

# Trovato nella tua Configuration Utility (screenshot "verdimetria")
INSTANCE_ID = "1ca53dc1-1760-4d9a-b80d-52f4d69602d7"
WMS_BASE_URL = f"https://sh.dataspace.copernicus.eu/ogc/wms/{INSTANCE_ID}"

# ID esatti visti nella tua lista di layer (colonna "Id" nello screenshot)
LAYERS = {
    "ndvi": "NDVI",
    "ndvi_gray": "NDVI-GRAY",           # probabilmente più vicino a un valore raw in scala di grigi
    "agriculture": "AGRICULTURE",
    "geology": "GEOLOGY",
    "moisture_index": "MOISTURE-INDEX",
    "evi": "EVI",
    "savi": "SAVI",
    "ndwi": "NDWI",
    "true_color": "TRUE-COLOR",
}

# Evalscript "raw" per NDVI: se decidi di creare un nuovo layer ad-hoc invece
# di riusare quello di visualizzazione, incolla questo nell'editor (pulsante
# "New Layer" -> Custom -> incolla nel campo evalscript):
RAW_NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "dataMask"] }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-9);
  return [ndvi];
}
""".strip()


def download_layer(
    layer_id: str,
    bbox_wgs84: list[float],
    output_path: str,
    date: str | None = None,
    width: int = 512,
    height: int = 512,
    max_cloud_cover: int = 20,
    image_format: str = "image/tiff",
) -> None:
    """
    Scarica un layer WMS come GeoTIFF su un'area e (opzionalmente) una data.

    bbox_wgs84: [west, south, east, north] in gradi (EPSG:4326).
    date: "YYYY-MM-DD" per un giorno preciso, oppure "YYYY-MM-DD/YYYY-MM-DD"
          per un intervallo (Sentinel Hub userà mosaic order per scegliere
          l'immagine, di norma la più recente/meno nuvolosa).

    NOTA: non testato con una chiamata di rete reale in questo ambiente
    (dominio dataspace.copernicus.eu non raggiungibile dalla sandbox).
    Verifica la prima esecuzione sulla tua macchina.
    """
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",  # con 1.1.1 il bbox è sempre in ordine lon,lat (evita l'ambiguità di assi di 1.3.0)
        "REQUEST": "GetMap",
        "LAYERS": layer_id,
        "BBOX": ",".join(str(v) for v in bbox_wgs84),
        "SRS": "EPSG:4326",
        "WIDTH": width,
        "HEIGHT": height,
        "FORMAT": image_format,
        "MAXCC": max_cloud_cover,
    }
    if date is not None:
        params["TIME"] = date

    response = requests.get(WMS_BASE_URL, params=params, timeout=60)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "xml" in content_type:
        # Il server WMS ritorna un errore come XML invece dell'immagine
        raise RuntimeError(f"Il server ha ritornato un errore invece di un'immagine:\n{response.text[:500]}")

    with open(output_path, "wb") as f:
        f.write(response.content)


def inspect_layer_values(tif_path: str) -> None:
    """
    Piccolo helper per capire subito se il GeoTIFF scaricato contiene valori
    raw (es. NDVI tra -1 e 1, una banda) o una visualizzazione RGB colorata
    (3 bande, valori 0-255) — esegui questo la prima volta su ogni layer
    prima di fidarti dei numeri nella pipeline.
    """
    import rasterio
    import numpy as np

    with rasterio.open(tif_path) as src:
        print(f"Bande: {src.count}, dtype: {src.dtypes[0]}")
        data = src.read(1)
        print(f"Banda 1 -> min={np.nanmin(data):.3f}, max={np.nanmax(data):.3f}, media={np.nanmean(data):.3f}")

        if src.count >= 3:
            print("⚠️  3+ bande rilevate: molto probabilmente è una visualizzazione RGB, non valori raw.")
        elif -1.5 <= np.nanmin(data) and np.nanmax(data) <= 1.5:
            print("✅ Range compatibile con un indice raw (es. NDVI tra -1 e 1).")
        else:
            print("⚠️  Range non tipico di un indice raw: verifica l'evalscript del layer.")
