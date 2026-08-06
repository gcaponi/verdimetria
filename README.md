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

Apri [verdimetria.cais.uno](https://verdimetria.cais.uno/). Il sistema reale è
live: registrazione email-first, disegno del campo su mappa, job di analisi
asincrono (Catalog → Statistical NDVI/NDMI → morfometria TINITALY 10m → land
cover CLC+ → AI agronomo DeepSeek), diario interventi, esportazione **report
agronomico PDF A4** generato server-side. Su `/demo` è pubblico un report
dimostrativo completo senza account (campo Innovagri reale).

API principali (Django, `https://api.verdimetria.cais.uno`):

- `POST /api/v1/auth/register/`, `POST /api/v1/auth/token/` - account e JWT;
- `GET|POST /api/v1/fields/` - campi tenant-scoped (max 3 per account, anti-abuso);
- `POST /api/v1/fields/{id}/jobs/`, `GET /api/v1/jobs/{id}/` - analisi asincrona;
- `GET /api/v1/jobs/{id}/report.pdf` - report agronomico A4 (owner-scoped, cache disco);
- `GET /api/v1/demo/` - report dimostrativo pubblico (AllowAny).

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

## Produzione (VPS `pcc`) — v1.0, 2026-07-30

Servizi systemd: `verdimetria.service` (gunicorn su `127.0.0.1:8001`, TLS via
nginx+certbot su `api.verdimetria.cais.uno`) e `verdimetria-celery.service`
(worker, concurrency 2, Redis db/1). PostgreSQL 16 + PostGIS 3.4 e Redis di
sistema. Frontend: Cloudflare Worker statico (`V2/`, deploy con
`npm run build && npx wrangler deploy`).

Deploy backend (dal 2026-08-06: `/opt/verdimetria` e' un clone git, come Zeus —
prima era rsync, che lasciava il server disallineato rispetto al repo):

```bash
ssh pcc "cd /opt/verdimetria && git pull -q origin main \
  && .venv/bin/pip install -r requirements.txt \
  && .venv/bin/python manage.py migrate \
  && sudo systemctl restart verdimetria verdimetria-celery"
```

Variabili `.env` rilevanti in produzione:

- `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` - OAuth Copernicus Data Space;
- `DEEPSEEK_API_KEY` - interpretazione AI (fallback rule-based se assente);
- `EMAIL_HOST=smtp-relay.brevo.com` + credenziali SMTP Brevo - email transazionali
  (mittente verificato `info@cais.uno`, DKIM+DMARC attivi);
- `TINITALY_CACHE_DIR=/opt/verdimetria/data/tinitaly` - cache lazy-tile DTM 10m;
- `CLC_PLUS_RASTER_PATH=/opt/verdimetria/data/clc/clc-plus-2021-italy-10m.tif`;
- `REPORT_CACHE_DIR` - cache PDF report (default `<BASE_DIR>/report-cache`);
- `MAX_FIELDS_PER_ACCOUNT=3` - cap anti-abuso campi per account;
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` - paywall abbonamenti Stripe;
- `STRIPE_PRICE_BASIC` / `STRIPE_PRICE_PRO` / `STRIPE_PRICE_PLUS` - price_id dei
  3 tier mensili (5/15/15+ ha). Senza questi valori checkout/portal/webhook
  falliscono, ma il gate 402 resta attivo per tutti i non abbonati.

Il campo demo pubblico è un `Field` con `is_demo=True` (flag solo via shell,
non esposto in API) + almeno un job completato; dopo ogni deploy che cambia il
contratto di analisi va rigenerato il job demo.

## Stato v1.0 e prossimi passi

La **v1.0** (tag git) chiude il prodotto osservativo da satellite: pipeline
quantitativa NDVI/NDMI/variabilità/morfometria/land-cover, AI agronomo con
evidenze, diario interventi, report PDF A4, demo pubblica, anti-abuso, email
transazionali. Suite 128 test verdi.

Il **paywall** (agosto 2026) attiva la monetizzazione: registrazione libera, ma
creazione campi e analisi richiedono un abbonamento Stripe a 3 tier mensili
(Basic 14,99 € fino a 5 ha, Pro 34,99 € fino a 15 ha, Plus 54,99 € illimitato).
Limite ettari **cumulativo** sui boundary correnti dei campi; disdetta libera
con accesso fino a scadenza (`cancel_at_period_end`). Pagina `/account` con
card piani, checkout/portal, webhook idempotente, gate 402; staff e campo demo
bypassano. Demo pubblica invariata.

Prossimi passi reali:

1. Validazione agronomica del report su campo reale (gate Fase 0 residuo) e
   pilot Innovagri/Sicilia.
2. Abbonamento stagionale (vendita manuale nel pilot, Stripe dopo validazione).
3. **V2.0** (spec nel PRD EterCervo, sezione 15): integrazione risultati
   analisi campioni di suolo (ground truth laboratorio) + AI Agronomo chat
   integrata con contesto completo per campo.
