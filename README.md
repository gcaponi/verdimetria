# Verdimetria

> **Stato al 2026-07-18:** vertical slice analitica pubblica e fondazione backend disponibile.
> `backend/` contiene Django/DRF, auth JWT, PostGIS, `Field` e `BoundaryVersion`;
> `src/` contiene il core geospaziale e gli adapter CDSE Catalog/Process/Statistical
> e ISPRA Litologia 1:100.000 validati live.
> `V2/` e' pubblicata su Cloudflare con Worker `/api/analyze`: Catalog e Statistical
> CDSE alimentano grafici NDVI reali e DeepSeek V4 Pro genera insight da metriche
> aggregate. Django/PostGIS resta locale finche' non viene scelto un host container
> con database PostGIS gestito.
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

✅ **Testato per davvero, gira:** `pytest` passa con 38 test. Sono coperti il
core raster, `AnalysisArea`, gli adapter CDSE Catalog/Process/Statistical e
ISPRA, auth,
tenancy, persistenza PostGIS e versionamento dei confini. Process e Statistical
API, Catalog STAC e ISPRA WFS sono stati chiamati live su AOI tecnici siciliani.
La stessa pipeline Catalog + Statistical + DeepSeek e' stata validata sul dominio
production, inclusi disegno campo, due grafici Recharts e AI con provenance.

⚠️ **Ancora da validare o consolidare:** SoilGrids quantitativo, Copernicus DEM
e S.I.T.R. regionale. Il primo run end-to-end deve usare un campo reale
autorizzato e risultati validati da chi conosce il campo.

La Carta Litologica ISPRA e' un **contesto nazionale 1:100.000**, non una misura
del terreno: gli attributi sono dichiarati dal provider ancora in validazione.
L'adapter conserva fonte, scala e licenza CC BY 4.0 e filtra sul Polygon reale.

## Prova online

Apri [verdimetria.cais.uno](https://verdimetria.cais.uno/). All'avvio viene
selezionata una AOI tecnica dimostrativa a Ragusa con dati satellitari reali.
Puoi:

- disegnare un rettangolo o un Polygon e avviare una nuova analisi;
- consultare scene Catalog, serie NDVI annuale e percentili dell'ultima data;
- aprire i due grafici nella tab **Vegetazione**;
- leggere tre insight nella tab **AI Insights**, con provider, modello ed evidenze;
- ispezionare layer WMS CDSE, SoilGrids e meteo.

L'API edge espone `GET /api/health` e `POST /api/analyze`. Le credenziali CDSE e
DeepSeek sono secret cifrati Cloudflare e non vengono inviate al browser.

## Il modulo WMS via Configuration Instance (verdimetria)

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

### Backend locale

```bash
docker compose up -d --wait db redis
python manage.py migrate
python manage.py runserver
```

Servizi locali: API `http://127.0.0.1:8000/api/v1/`, PostGIS su `5433` e
Redis su `6380`, entrambi in ascolto solo su localhost. Endpoint iniziali:

- `POST /api/v1/auth/register/` - account email-first;
- `POST /api/v1/auth/token/` e `POST /api/v1/auth/token/refresh/` - JWT;
- `GET|POST /api/v1/fields/` - elenco tenant-scoped e creazione campo;
- `POST /api/v1/fields/{id}/boundaries/` - nuova versione del confine.

Il payload di creazione campo usa `name` e `boundary` GeoJSON. Sono accettati
solo Polygon/MultiPolygon WGS84 validi; superficie e CRS UTM locale vengono
calcolati server-side e il confine viene normalizzato in PostGIS.

Provider iniziali per i dati reali:
- **Copernicus Data Space Ecosystem** (Sentinel-2, DEM): https://dataspace.copernicus.eu/
- **Geoportale S.I.T.R. Sicilia**: nessuna registrazione per WMS/WFS pubblici, esplora il catalogo su https://www.sitr.regione.sicilia.it/geoportale/it/home/servicecatalog
- **ISPRA Carta Litologica 1:100.000**: WMS/WFS pubblico scoped su
  `https://sgi2.isprambiente.it/geoserver/ge-core8/ows`, CC BY 4.0 salvo
  eccezioni specifiche, attribuzione e URL obbligatori.
- **SoilGrids**: nessuna registrazione, ma nota che l'API REST a punti è
  attualmente sospesa da ISRIC — il modulo usa la via WCS (raster), che è
  comunque quella giusta per la nostra architettura a stack.

Il prodotto non e' vincolato alle fonti gratuite. `.env.example` include anche
gli slot per Planet, UP42, Vantor, OpenTopography OT+, Meteomatics, MapTiler,
object storage S3/R2, DeepSeek V4 Pro, Postmark, Stripe e Sentry. Ogni provider
premium va attivato solo dopo contratto, EULA e costo per ettaro misurato.

## Demo sintetica locale

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
    catalog_api.py             - ricerca STAC Polygon-first, cloud filter e paginazione
    ispra_lithology.py         - contesto litologico 1:100.000 WFS, filtro Polygon e provenance
    sentinel_hub_wms.py        - layer già processati (NDVI, Agricoltura, Geologia...) via la
                                  tua Configuration Instance "verdimetria" (Instance ID incluso)
    process_api.py             - CONSIGLIATO per dati quantitativi: Process API con evalscript
                                  tuo (NDVI raw FLOAT32 su L2A), bypassa l'ambiguità dei preset WMS
  viz/                         - (da popolare: export mappa riutilizzabile)
demo/run_synthetic_demo.py     - pipeline completa con dati sintetici
tests/test_raster_stack.py     - test del motore core
```

## Prossimi passi realistici

1. Collegare il disegno mappa a `POST /api/v1/fields/` e correggere il conflitto
  touch tra drawing e pan su mobile.
2. Aggiungere `AnalysisJob` idempotente e worker Celery, riusando Catalog,
  Process, Statistical e ISPRA gia' validati.
3. Ottenere il confine di un campo reale autorizzato e chiudere la Fase 0 con
  una validazione agronomica esplicita.
4. Validare SoilGrids, Copernicus DEM e S.I.T.R.; mantenere ISPRA come contesto
  1:100.000 e aggiungere analisi di laboratorio/ground truth per decisioni reali.
5. Alimentare grafici e AI Insights solo da metriche backend con provenienza,
  quality score e limiti dichiarati.
