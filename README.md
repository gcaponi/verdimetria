# VerdiMetria

> **Stato al 2026-07-16:** repository di partenza, non prodotto pronto.
> `src/` contiene un prototipo analitico Python da estrarre e validare su dati reali;
> `V2/` e' una reference UX React basata interamente su dati sintetici.
> Copernicus, SoilGrids e S.I.T.R. non sono ancora collegati a una pipeline di prodotto.
> Non usare i risultati correnti per diagnosi o prescrizioni agronomiche.

Sistema per leggere in modo integrato dati geologici e agricoli sul
territorio di Ragusa: un modulo per far emergere anomalie geologiche
multivariate (senza bisogno di depositi noti su cui addestrarsi) e un modulo
per individuare debolezze croniche del suolo agricolo e ipotizzare quale
sostanza (azoto, pH, carbonio organico...) ne sia la causa più probabile.

## Perché questa architettura (e cosa ho preso dai repo di riferimento)

Ho ispezionato tre progetti open source di mineral prospectivity mapping
prima di scrivere questo codice:

- **[Abdallah-M-Ali/Mineral-Prospectivity-Mapping-ML](https://github.com/Abdallah-M-Ali/Mineral-Prospectivity-Mapping-ML)**
  — pipeline pulita RF/SVM/ANN/CNN per prospezione aurifera in Sudan. Da qui
  ho preso il **pattern centrale**: rasterizzare le etichette sulla griglia
  del raster, estrarre (X, y) solo dove ci sono dati validi, addestrare,
  predire sull'intera immagine, rimettere in forma 2D, scrivere GeoTIFF.
  Vedi `src/core/raster_stack.py`.
- **[mheriyanto/machine-learning-in-mineral-exploration](https://github.com/mheriyanto/machine-learning-in-mineral-exploration)**
  e **[RichardScottOZ/mineral-exploration-machine-learning](https://github.com/RichardScottOZ/mineral-exploration-machine-learning)**
  — più che codice, sono raccolte curate di riferimenti/paper. Utili come
  bibliografia, non come base di codice.

**Cosa NON ho preso**: nessuno dei tre presuppone un'area senza depositi noti
etichettati, che è esattamente il nostro caso per Ragusa. Il codice originale
di Abdallah-M-Ali inoltre usa binding gdal/ogr grezze, path Windows
hardcoded, e una chiamata numpy (`np.int`) rimossa dalle versioni recenti di
NumPy. Qui è stato tutto riscritto con rasterio/geopandas, reso
parametrico, e reso **unsupervised di default** nel modulo geologico
(`src/geo_module/anomaly_detection.py`, IsolationForest + PCA) — perché
senza depositi noti un classificatore supervisionato semplicemente non ha
nulla su cui addestrarsi. Se un giorno avrai punti di verità nota (analisi di
laboratorio, log di pozzi storici), `rasterize_labels()` in
`raster_stack.py` ti permette di passare a un approccio supervisionato con
lo stesso motore.

## Cosa è stato testato, e cosa no (leggi questo prima di fidarti del codice)

Questo progetto è stato scritto in un ambiente sandboxed con accesso di rete
limitato a PyPI/GitHub (nessun accesso a Copernicus, ISRIC, geoportale
siciliano). Quindi:

✅ **Testato per davvero, gira** (vedi `demo/run_synthetic_demo.py`):
il motore core (`raster_stack.py`), il modulo geologico, il modulo agricolo,
l'esportazione della mappa — tutto con dati sintetici ma georeferenziati
realmente sul bounding box di Ragusa. `pytest tests/` passa (4/4).

⚠️ **Scritto secondo la documentazione ufficiale, MAI chiamato dal vivo**:
i tre moduli in `src/ingestion/` (SoilGrids, Sentinel-2/CDSE, Geoportale
Sicilia). Sono corretti sulla carta, ma la prima esecuzione reale la farai
tu: aspettati di dover aggiustare qualche dettaglio (nomi esatti dei layer
WMS, formato bbox richiesto dal server WCS, ecc.).

## Il modulo WMS via Configuration Instance (ragusa-geo-intel)

Hai creato una Configuration Instance su Sentinel Hub (Instance ID
`1ca53dc1-1760-4d9a-b80d-52f4d69602d7`, template "Full WMS") che espone
layer già processati — NDVI, Agricoltura, Geologia, Moisture Index, EVI,
SAVI, NDWI — senza dover scaricare e processare tu le bande grezze.
`src/ingestion/sentinel_hub_wms.py` costruisce le richieste WMS verso questa
istanza (URL verificato per correttezza, non ancora chiamato dal vivo per lo
stesso motivo di rete spiegato sopra).

**⚠️ Verifica prima di fidarti dei numeri**: i layer come NDVI nel template
Full WMS sono storicamente pensati per la *visualizzazione* su mappa
(colori RGB su scala cromatica), non per il valore numerico grezzo
dell'indice. Esempio concreto verificato sul tuo layer "Agriculture": è
letteralmente un composito bande 11/8A/2 mappate su RGB per l'ispezione
visiva, calcolato su Sentinel-2 **L1C** (non corretto atmosfericamente) —
buono per guardarlo su una mappa, inutilizzabile per un'analisi quantitativa.

**Per questo ho aggiunto `src/ingestion/process_api.py`**, che è la via
consigliata per il modulo agricolo: invii tu l'evalscript (NDVI raw,
output FLOAT32, su collezione L2A corretta atmosfericamente), quindi non hai
nessuna ambiguità su cosa stai davvero scaricando. Richiede le stesse
credenziali CDSE_CLIENT_ID/SECRET già nel tuo `.env`.

Se preferisci comunque restare sui layer WMS della tua configurazione (es.
per la visualizzazione rapida su mappa), usa `inspect_layer_values()` in
`sentinel_hub_wms.py` per verificare ogni volta cosa hai davvero scaricato.

## Setup

```bash
python -m venv venv
source venv/bin/activate  # su Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # poi riempi CDSE_CLIENT_ID / CDSE_CLIENT_SECRET
```

Registrazioni gratuite necessarie per i dati reali:
- **Copernicus Data Space Ecosystem** (Sentinel-2, DEM): https://dataspace.copernicus.eu/
- **Geoportale S.I.T.R. Sicilia**: nessuna registrazione per WMS/WFS pubblici, esplora il catalogo su https://www.sitr.regione.sicilia.it/geoportale/it/home/servicecatalog
- **SoilGrids**: nessuna registrazione, ma nota che l'API REST a punti è
  attualmente sospesa da ISRIC — il modulo usa la via WCS (raster), che è
  comunque quella giusta per la nostra architettura a stack.

## Prova subito (senza credenziali, senza dati reali)

```bash
python -m demo.run_synthetic_demo
```

Genera `outputs/geo_anomaly_score.tif`, `outputs/agro_weakness_score.tif`
e `outputs/ragusa_map.html` — apri quest'ultimo in un browser per vedere
entrambi i layer su una mappa interattiva. Serve solo a dimostrare che
l'architettura regge; i numeri sono casuali.

## Struttura

```
src/
  config.py                    - AOI di Ragusa, CRS di lavoro, costanti
  core/raster_stack.py         - motore generico: carica/allinea/preddici/scrivi raster
  geo_module/anomaly_detection.py  - IsolationForest + PCA, unsupervised
  agro_module/soil_weakness.py     - NDVI nel tempo + attribuzione fattore limitante
  ingestion/
    sicilia_geoportale.py      - WMS/WFS via owslib
    soilgrids_client.py        - proprietà del suolo via WCS
    sentinel2_cdse.py          - Sentinel-2 via Copernicus Data Space Ecosystem (STAC+OAuth, scene grezze)
    sentinel_hub_wms.py        - layer già processati (NDVI, Agricoltura, Geologia...) via la
                                  tua Configuration Instance "ragusa-geo-intel" (Instance ID incluso)
    process_api.py             - CONSIGLIATO per dati quantitativi: Process API con evalscript
                                  tuo (NDVI raw FLOAT32 su L2A), bypassa l'ambiguità dei preset WMS
  viz/                         - (da popolare: export mappa riutilizzabile)
demo/run_synthetic_demo.py     - pipeline completa con dati sintetici
tests/test_raster_stack.py     - test del motore core
```

## Prossimi passi realistici

1. Sostituisci il bounding box approssimativo in `config.py` con un confine
   amministrativo reale (ISTAT).
2. Registrati su CDSE e prova `sentinel2_cdse.py` per scaricare 2-3 scene
   reali su Ragusa.
3. Esplora il catalogo del Geoportale S.I.T.R. per trovare i nomi esatti dei
   layer geologici che ti servono (litologia, geositi...).
4. Rilancia `demo/run_synthetic_demo.py` sostituendo via via i file sintetici
   con quelli reali in `data/raw/` — la pipeline core non cambia.
5. Qualsiasi anomalia o zona debole emerga, trattala come **ipotesi da
   validare** (con un geologo per il modulo geo, con un'analisi di
   laboratorio per il modulo agro) — non come una conclusione.
