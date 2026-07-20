# Verdimetria - runbook per l'operativita' production

> Stato verificato: 2026-07-18. Questo documento elenca account, credenziali,
> contratti, componenti e gate necessari. Non contiene segreti reali.

## Verdetto attuale

La fondazione tecnica e' valida, ma Verdimetria non e' ancora operativa al 100%.
Sono verificati Django/DRF/PostGIS, JWT, tenancy, versionamento dei confini,
CDSE Catalog/Process/Statistical, UTM locale e ISPRA Carta Litologica. Il gate
automatico e' verde con 38 test, nessun drift di migrazione e nessun errore di
sistema.

I blocchi reali sono:

1. un campo autorizzato con Polygon/GeoJSON, proprietario e finalita' definite;
2. un agronomo o tecnico che validi i risultati sul campo;
3. `AnalysisJob`, Celery, object storage e API di stato/risultato;
4. collegamento completo del frontend a backend, grafici e AI Insights reali;
5. deploy production, sicurezza account, backup, monitoring e runbook incidenti;
6. validazione quantitativa di suolo, DEM e meteo sul pilot reale.

Nessuna combinazione di credenziali sostituisce i primi due punti.

## Stack consigliato

### Stack minimo di lancio

| Area | Scelta | Motivo |
| --- | --- | --- |
| Frontend | Cloudflare Pages sul dominio Verdimetria | Gia' in uso, CDN e deploy atomici |
| API e worker | Container paid in regione UE, separando web e Celery | Deploy ripetibile e scaling indipendente |
| Database | PostgreSQL/PostGIS gestito con PITR | Geometrie, tenancy, backup e restore affidabili |
| Queue/cache | Redis gestito con persistenza dove richiesta | Job asincroni, retry e rate limit |
| Raster/result | Cloudflare R2 EU o S3 EU | Asset grandi fuori dal database, URL firmati |
| Satellite baseline | Copernicus Data Space Ecosystem | Sentinel-2 L2A quantitativo e catalogo reale |
| Basemap/geocoding | MapTiler paid con key protetta per origin | Mappa stabile, quote e supporto commerciale |
| Meteo | Meteomatics enterprise | Point/polygon, storico, forecast, parametri agricoli |
| AI | DeepSeek API, `deepseek-v4-pro` | Insight testuali server-side con costo controllabile |
| Email | Postmark | Verifica email, reset password e notifiche job |
| Monitoring | Sentry backend/frontend piu' metriche infrastrutturali | Errori, release e performance |
| Billing | Stripe | Checkout, abbonamenti e webhook firmati |

Il container provider e il database provider non sono ancora scelti. Il requisito
non negoziabile e' una regione UE, TLS, backup automatici, restore testabile,
metriche, log esportabili e supporto PostGIS. Evitare una VPS singola come unico
punto di errore quando iniziano i clienti paganti.

### Strategia dati senza vincolo "solo gratuito"

1. **Baseline:** CDSE Sentinel-2 L2A resta sempre disponibile e tracciabile.
2. **Primo upgrade paid:** Planet diretto per monitoraggio ottico frequente e
   coerente su aziende agricole selezionate.
3. **Broker premium:** UP42 per acquistare una tantum VHR, SAR, thermal,
   hyperspectral, elevation o tasking da piu' vendor senza integrare ogni
   catalogo separatamente.
4. **Direct enterprise:** Vantor solo quando un cliente richiede risoluzione,
   archivio o SLA specifici non coperti dal broker.
5. **Weather:** Meteomatics per dati enterprise; la fonte pubblica puo' restare
   come fallback e confronto, non come unico servizio operativo.
6. **DEM:** Copernicus DEM per la baseline; OpenTopography OT+ o dataset
   Airbus/Vantor/territoriali quando la risoluzione del caso d'uso lo richiede.

Non integrare Planet, UP42 e Vantor contemporaneamente prima di avere un caso
pagante. Ogni adapter aggiunge EULA, costi, quote, retry e supporto operativo.

## Matrice credenziali

### Core e deploy

| Servizio | Variabili | Tipo | Dove si ottiene | Stato |
| --- | --- | --- | --- | --- |
| Django | `DJANGO_SECRET_KEY` | Segreto server | Generata con CSPRNG, distinta per ambiente | Richiesta |
| Django | `DJANGO_ALLOWED_HOSTS` | Config | Domini API production/staging | Richiesta |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Password server | Provider database gestito | Richiesta |
| Redis | `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | URL segreti | Provider Redis gestito | Richiesta |
| Cloudflare deploy | `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Segreto CI | Dashboard Cloudflare, token scoped al progetto | Richiesta |
| R2/S3 | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `S3_REGION` | Segreto server | R2 API Tokens o IAM equivalente | Richiesta con AnalysisJob |

Per production aggiungere un `JWT_SIGNING_KEY` separato dal segreto Django e
configurare rotazione e `kid`; oggi SimpleJWT usa la configurazione Django.

### Dati, mappe e AI

| Servizio | Variabili | Tipo | Autenticazione e note | Stato |
| --- | --- | --- | --- | --- |
| CDSE | `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` | Segreto server | OAuth2 client credentials; token cached fino a scadenza | Attivo e live-validato |
| ISPRA | Nessuna | Pubblico | WMS/WFS scoped `ge-core8`; CC BY 4.0 e attribuzione | Attivo e live-validato |
| S.I.T.R. Sicilia | Nessuna per i layer pubblici | Pubblico | Verificare licenza e semantica per singolo layer | Da validare |
| SoilGrids | Nessuna per WCS | Pubblico | Quantitativo a 250 m; dichiarare risoluzione e incertezza | Da validare |
| MapTiler | `VITE_MAPTILER_API_KEY` | Pubblica limitata | Chiave production protetta per HTTP origin; una key per app | Da acquistare/configurare |
| DeepSeek | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL=deepseek-v4-pro` | Segreto server | Bearer API key; mai dal browser | Account pronto, adapter da implementare |
| Meteomatics | `METEOMATICS_USERNAME`, `METEOMATICS_PASSWORD` | Segreto server | Credenziali enterprise; piano dati/SLA contrattuale | Contratto da richiedere |
| Planet | `PL_API_KEY` | Segreto server | API key da account; HTTP Basic preferito per `api.planet.com` | Contratto opzionale |
| UP42 | `UP42_USERNAME`, `UP42_PASSWORD` | Segreto server | Token Bearer 5 minuti via password flow; usare account tecnico dedicato | Contratto opzionale |
| Vantor | `VANTOR_API_KEY` | Segreto server | API key fino a 180 giorni; preferita al password flow | Contratto opzionale |
| OpenTopography | `OPENTOPOGRAPHY_API_KEY` | Segreto server | API key e piano OT+ per uso commerciale/quote superiori | Opzionale |

Note operative:

- Planet documenta `PL_API_KEY` e raccomanda oggi API key per M2M su
  `api.planet.com`; OAuth2 M2M e' pienamente disponibile sui servizi Sentinel
  Hub Planet ma non ancora su tutti gli endpoint Planet Data/Orders.
- UP42 richiede attualmente email/password per generare token di 5 minuti.
  Creare un utente tecnico senza privilegi amministrativi e non riusare le
  credenziali personali di Guglielmo.
- Vantor sospende gli account dopo 90 giorni di inattivita': prevedere un
  controllo periodico documentato, non traffico artificiale incontrollato.
- La key MapTiler e' visibile nel browser per definizione: la sicurezza viene
  da allowed origins, quote e key separata per ambiente.

### Comunicazioni, billing e monitoring

| Servizio | Variabili | Tipo | Configurazione richiesta | Stato |
| --- | --- | --- | --- | --- |
| Postmark | `POSTMARK_SERVER_TOKEN`, `DEFAULT_FROM_EMAIL` | Segreto server | Sender/domain verificato, DKIM e Return-Path | Da attivare |
| Stripe | `STRIPE_RESTRICTED_KEY`, `STRIPE_WEBHOOK_SECRET` | Segreto server | Restricted key minima e webhook separato per ambiente | Da attivare |
| Stripe frontend | `VITE_STRIPE_PUBLISHABLE_KEY` | Pubblica | Publishable key dell'ambiente corretto | Da attivare |
| Sentry backend | `SENTRY_DSN` | DSN server | Progetto Django, environment e release | Da attivare |
| Sentry frontend | `VITE_SENTRY_DSN` | DSN pubblico limitato | Progetto React, release e source map protette | Da attivare |

## Ordine di apertura account

1. Scegliere provider container UE, PostgreSQL/PostGIS gestito e Redis gestito.
2. Creare ambienti separati `staging` e `production`, con database e bucket
   distinti.
3. Configurare Cloudflare DNS/Pages e token CI con i soli permessi necessari.
4. Creare bucket R2 EU, lifecycle, CORS e credenziali per singolo ambiente.
5. Creare client CDSE production separato da sviluppo e configurare quote alert.
6. Creare key MapTiler production protetta per `https://verdimetria.cais.uno`
   e per l'eventuale dominio definitivo.
7. Verificare dominio Postmark e implementare verifica email/reset password.
8. Creare progetti Sentry frontend/backend e release mapping.
9. Creare account DeepSeek e un budget mensile; attivare l'adapter solo dopo
   avere output strutturati, provenance e disclaimer.
10. Aprire Stripe in test, completare KYC e passare live solo dopo webhook
    idempotenti e riconciliazione abbonamenti.
11. Richiedere offerte Meteomatics e Planet sul volume del pilot; usare UP42
    per acquisti specialistici invece di contrattualizzare subito ogni vendor.
12. Attivare OpenTopography OT+ o DEM premium solo se il pilot dimostra che il
    DEM baseline non basta.

## Requisiti contrattuali da chiedere ai provider paid

Per ogni offerta richiedere per iscritto:

- diritto di usare, elaborare e mostrare derivati ai clienti finali;
- regole su caching, redistribuzione, retention e cancellazione dei raster;
- territorio coperto, latenza, revisit e disponibilita' storica;
- risoluzione nativa, processing level, bande, cloud mask e quality metadata;
- prezzo per km2/scena/chiamata, minimum order e overage;
- quote API, concorrenza, rate limit e tempi di consegna;
- SLA, supporto, incident notification e data residency;
- DPA/GDPR, subprocessors, trasferimenti extra UE e termini di cessazione;
- ownership dei derivati e possibilita' di usarli in report commerciali;
- ambiente sandbox o sample imagery per test di accettazione.

Non firmare un contratto immagini basandosi solo sulla risoluzione nominale.
Per agricoltura contano anche calibrazione radiometrica, coerenza temporale,
cloud/shadow mask, frequenza utile e licenza sui derivati.

## Gestione segreti

- Nessun segreto in Git, browser, ticket, wiki o chat.
- Vault centralizzato con accesso nominativo, audit e MFA.
- Segreti diversi per local, staging e production.
- Account tecnici dedicati; nessuna password personale in un worker.
- Token CI e cloud limitati per risorsa e azione.
- Rotazione documentata: immediata su incidente, periodica per chiavi statiche.
- Log redaction per header `Authorization`, password, token e URL firmati.
- Secret scanning in CI e blocco push sui pattern noti.
- Chiavi pubbliche frontend protette con origin, quote e alert di spesa.

## Gate tecnici di go-live

### Backend e infrastruttura

- `DEBUG=false`, host/CORS/CSRF espliciti, TLS end-to-end e HSTS.
- Cookie secure, proxy header corretti e limiti body/upload.
- PostgreSQL con SSL, backup automatico, PITR e restore provato.
- Redis non esposto pubblicamente, autenticato e con policy di memoria.
- Web e worker separati; job idempotenti, retry con backoff e dead-letter path.
- Raster in object storage, checksum, metadata, retention e URL firmati.
- Health/readiness endpoint per web, database, Redis e provider essenziali.
- Rate limiting per auth, analisi e provider esterni.
- Deploy con migrazioni controllate e rollback applicativo testato.

### Account e sicurezza prodotto

- Verifica email, reset password e revoca/rotazione refresh token.
- Lockout/rate limit anti brute force e MFA per operatori amministrativi.
- Ruoli espliciti per owner, agronomo, operatore e viewer.
- Audit log per confini, analisi, report e accessi amministrativi.
- Export e cancellazione account/dati secondo policy GDPR.
- Test di tenancy su ogni endpoint e asset firmato.

### Dati e scienza

- Ogni metrica conserva provider, dataset, scena, timestamp, CRS, unita',
  risoluzione, processing level, quality flags e versione algoritmo.
- Cloud/shadow/no-data esclusi; copertura utile e data di acquisizione visibili.
- ISPRA mostrato solo come contesto 1:100.000, mai come analisi del suolo.
- AI Insights ricevono solo metriche validate e restituiscono output strutturato
  con evidenze, limiti e divieto di diagnosi/prescrizione automatica.
- Confronto con analisi di campo/laboratorio e validazione agronomica firmata.
- Test di regressione su almeno tre campi, stagioni e colture rappresentative.

### Prodotto e supporto

- Drawing mobile disabilita il pan durante il gesto e funziona su iOS/Android.
- Grafici usano dati backend reali e gestiscono empty/loading/error/stale.
- Report con attribuzioni/licenze, data freshness e disclaimer scientifico.
- Monitoring, alert, runbook incidenti, status page e canale supporto.
- Cost cap per tenant/provider e blocco esplicito prima di ordini premium.
- Privacy policy, termini, DPA, cookie policy e registro trattamenti approvati.

## Gate del pilot reale

Raccogliere e approvare questi dati con
[`pilot-intake-template.md`](pilot-intake-template.md) prima del primo run.

Il pilot e' accettabile solo quando sono disponibili:

1. Polygon/GeoJSON del campo e conferma WGS84;
2. nome del proprietario/gestore e autorizzazione documentata;
3. coltura, ciclo, date note, irrigazione e interventi recenti;
4. visibilita' consentita del report e periodo di conservazione;
5. agronomo/tecnico responsabile della validazione;
6. almeno un riscontro indipendente: sopralluogo, analisi laboratorio o sensore;
7. criteri di successo concordati prima di guardare i risultati.

Fino a quel momento gli AOI tecnici dimostrano che le API funzionano, non che il
prodotto produce conclusioni agronomiche affidabili.

## Budget e controllo costi

Preparare un foglio costi mensile con almeno:

- compute web e worker;
- PostgreSQL/PostGIS, Redis, backup e traffico;
- object storage, operazioni e egress;
- MapTiler richieste mappa/geocoding;
- CDSE quote e Planet/UP42/Vantor per km2 o scena;
- Meteomatics per chiamata/parametro/piano;
- DeepSeek per token e retry;
- Postmark per email, Sentry per eventi e Stripe per transazione;
- supporto umano e validazione agronomica.

Ogni ordine premium deve avere stima preventiva, tenant, commessa, approvatore,
massimale e riconciliazione del costo reale. Senza questi campi il provider paid
non entra nel flusso automatico.

## Fonti ufficiali verificate

- CDSE APIs: <https://documentation.dataspace.copernicus.eu/APIs.html>
- CDSE OAuth: <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html>
- DeepSeek models: <https://api-docs.deepseek.com/quick_start/pricing>
- Planet authentication: <https://docs.planet.com/develop/authentication/>
- Planet Data API: <https://docs.planet.com/develop/apis/data/>
- Planet Orders API: <https://docs.planet.com/develop/apis/orders/>
- UP42 authentication: <https://docs.up42.com/developers/authentication>
- UP42 collections: <https://docs.up42.com/data/collections>
- Vantor authentication: <https://developers.maxar.com/docs/authentication/>
- Meteomatics Weather API: <https://www.meteomatics.com/en/weather-api/>
- MapTiler key protection: <https://docs.maptiler.com/cloud/api/authentication-key/>
- OpenTopography API: <https://portal.opentopography.org/apidocs/>
- Cloudflare R2 S3 credentials: <https://developers.cloudflare.com/r2/api/s3/tokens/>
- Postmark server tokens: <https://postmarkapp.com/developer/user-guide/send-email-with-api/send-a-single-email>
- Stripe API keys: <https://docs.stripe.com/keys>
- Stripe webhook signatures: <https://docs.stripe.com/webhooks/signature>
- Sentry DSN: <https://docs.sentry.io/concepts/key-terms/dsn-explainer/>

## Definition of done

Verdimetria e' "operativa al 100%" soltanto quando tutti i gate tecnici,
scientifici, legali e di supporto sono chiusi in production e il pilot reale e'
firmato dal validatore. L'acquisto dei servizi premium migliora disponibilita' e
qualita', ma non cambia questa definizione.
