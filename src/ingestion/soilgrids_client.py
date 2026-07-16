"""
Client per SoilGrids (ISRIC) — proprietà del suolo globali a 250m: pH,
azoto totale, carbonio organico, tessitura (sabbia/limo/argilla), CEC, ecc.

ATTENZIONE (verificato al momento di scrivere questo modulo): l'API REST
"a punti" di ISRIC (rest.isric.org/soilgrids/v2.0/properties/query) è
temporaneamente sospesa per problemi lato ISRIC, senza ETA di ripristino.
Per questo motivo qui usiamo la via WCS (Web Coverage Service) tramite il
pacchetto `soilgrids`, che scarica il raster direttamente per un'area
(bounding box) invece di un singolo punto — che è comunque quello che ci
serve per il nostro raster stack, quindi non è un downgrade.

Se in futuro l'API REST a punti torna disponibile e ti serve solo un valore
puntuale (es. per validare un singolo campione di laboratorio), vedi:
https://rest.isric.org/soilgrids/v2.0/docs

Proprietà disponibili (nome_variabile): bdod (bulk density), cec, cfvo
(frammenti grossolani), clay, nitrogen, phh2o, sand, silt, soc (carbonio
organico), ocd, ocs, wv0010/wv0033/wv1500 (contenuto idrico a varie tensioni).
"""

from __future__ import annotations

from soilgrids import SoilGrids

# CRS nativo usato dai tile WCS di SoilGrids (Homolosine); la libreria si
# occupa di riproiettare in output se serve, ma le bbox in input vanno date
# in questo sistema oppure va usato un CRS che owslib/soilgrids sappia convertire.
SOILGRIDS_HOMOLOSINE_CRS = "urn:ogc:def:crs:EPSG::152160"


def fetch_soil_property(
    property_id: str,
    coverage_id: str,
    bbox_wgs84: list[float],
    output_path: str,
) -> None:
    """
    Scarica un layer di proprietà del suolo per un'area, come GeoTIFF.

    property_id: es. "phh2o", "nitrogen", "soc", "clay"...
    coverage_id: es. "phh2o_0-5cm_mean" (proprietà_profondità_statistica)
    bbox_wgs84: [west, south, east, north] in gradi (EPSG:4326) — verrà
        convertito internamente; per un controllo più fine sulla proiezione
        usa direttamente il pacchetto `soilgrids` con coordinate Homolosine.
    output_path: dove salvare il GeoTIFF risultante.

    NOTA: non testato con una chiamata di rete reale in questo ambiente
    (dominio isric.org non raggiungibile dalla sandbox). Verifica la prima
    esecuzione sulla tua macchina e controlla i log per eventuali cambi di
    formato bbox richiesti dal server WCS.
    """
    import pyproj

    to_homolosine = pyproj.Transformer.from_crs("EPSG:4326", "ESRI:54052", always_xy=True)
    west, south, east, north = bbox_wgs84
    xs, ys = to_homolosine.transform([west, east], [south, north])

    client = SoilGrids()
    client.get_coverage_data(
        service_id=property_id,
        coverage_id=coverage_id,
        west=xs[0], south=ys[0], east=xs[1], north=ys[1],
        crs=SOILGRIDS_HOMOLOSINE_CRS,
        output=output_path,
    )


# Set consigliato di proprietà per il modulo agricolo (0-5cm, la profondità
# più rilevante per la vitalità delle colture superficiali):
RECOMMENDED_PROPERTIES_0_5CM = {
    "phh2o": "phh2o_0-5cm_mean",       # pH
    "nitrogen": "nitrogen_0-5cm_mean",  # azoto totale
    "soc": "soc_0-5cm_mean",            # carbonio organico
    "clay": "clay_0-5cm_mean",          # % argilla (tessitura/drenaggio)
    "cec": "cec_0-5cm_mean",            # capacità di scambio cationico
}
