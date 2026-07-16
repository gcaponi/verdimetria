"""
Client per il Geoportale S.I.T.R. (Sistema Informativo Territoriale
Regionale) della Regione Siciliana, che espone la Cartografia Geologica
Regionale e altre banche dati via servizi OGC standard (WMS/WFS/WCS).

Catalogo servizi: https://www.sitr.regione.sicilia.it/geoportale/it/home/servicecatalog

NOTA IMPORTANTE: questo modulo usa owslib, la libreria standard per parlare
con servizi OGC (usata anche da QGIS). Il codice qui è corretto secondo la
documentazione OGC/owslib, ma il dominio del geoportale NON è raggiungibile
dalla sandbox in cui è stato scritto (rete limitata a PyPI/GitHub/npm) quindi
NON è stato validato con una chiamata live. Testalo per primo sulla tua
macchina prima di costruirci sopra: la struttura esatta dei layer (nomi,
namespace) va comunque scoperta esplorando get_capabilities().
"""

from __future__ import annotations

from owslib.wfs import WebFeatureService
from owslib.wms import WebMapService


def get_wms_capabilities(wms_url: str, version: str = "1.3.0") -> WebMapService:
    """
    Connette a un endpoint WMS e ritorna l'oggetto servizio, da cui puoi
    ispezionare .contents (i layer disponibili) prima di scaricare qualcosa.

    Esempio d'uso:
        wms = get_wms_capabilities("https://<url-wms-del-geoportale>")
        print(list(wms.contents))  # elenco layer disponibili
    """
    return WebMapService(wms_url, version=version)


def download_wms_layer(
    wms_url: str,
    layer_name: str,
    bbox: list[float],
    output_path: str,
    width: int = 2048,
    height: int = 2048,
    image_format: str = "image/geotiff",
    crs: str = "EPSG:4326",
) -> None:
    """
    Scarica un layer WMS come immagine georeferenziata (GeoTIFF se il server
    lo supporta, altrimenti prova "image/tiff" o "image/png" + world file).

    bbox: [west, south, east, north] nello stesso CRS specificato in `crs`.
    """
    wms = get_wms_capabilities(wms_url)
    response = wms.getmap(
        layers=[layer_name],
        srs=crs,
        bbox=tuple(bbox),
        size=(width, height),
        format=image_format,
    )
    with open(output_path, "wb") as f:
        f.write(response.read())


def get_wfs_capabilities(wfs_url: str, version: str = "2.0.0") -> WebFeatureService:
    """Connette a un endpoint WFS (dati vettoriali: geositi, confini, ecc.)."""
    return WebFeatureService(wfs_url, version=version)


def download_wfs_features(
    wfs_url: str,
    type_name: str,
    output_path: str,
    bbox: list[float] | None = None,
    output_format: str = "application/json",
) -> None:
    """
    Scarica le feature vettoriali di un layer WFS (es. il catalogo dei geositi)
    come GeoJSON, pronto per essere letto con geopandas.read_file().
    """
    wfs = get_wfs_capabilities(wfs_url)
    kwargs = {"typename": type_name, "outputFormat": output_format}
    if bbox is not None:
        kwargs["bbox"] = tuple(bbox)

    response = wfs.getfeature(**kwargs)
    with open(output_path, "wb") as f:
        f.write(response.read())


# Endpoint noti da avviare l'esplorazione (verifica sempre nel catalogo,
# alcuni layer richiedono URL specifici per singolo dataset):
KNOWN_ENDPOINTS = {
    "catalogo_servizi": "https://www.sitr.regione.sicilia.it/geoportale/it/home/servicecatalog",
    "protezione_civile_wms": "https://www.protezionecivilesicilia.it (vedi sezione Consulta i dati con il WMS)",
    "servizio_geologico_italia": "https://portalesgi.isprambiente.it/it/node/143/",
}
