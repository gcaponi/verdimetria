import proj4 from "proj4";

type Position = [number, number];

interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

interface AnalyzeRequest {
  geometry: PolygonGeometry;
  startDate?: string;
  endDate?: string;
}

interface Env {
  ASSETS: { fetch(request: Request): Promise<Response> };
  CDSE_CLIENT_ID: string;
  CDSE_CLIENT_SECRET: string;
  DEEPSEEK_API_KEY: string;
  DEEPSEEK_MODEL?: string;
}

interface StatisticalPoint {
  date: string;
  from: string;
  to: string;
  mean: number;
  min: number;
  max: number;
  stDev: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  validPixels: number;
}

interface Insight {
  tone: "alert" | "warn" | "ok" | "info";
  title: string;
  text: string;
  evidence: string;
}

const TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token";
const CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search";
const STATISTICAL_URL = "https://sh.dataspace.copernicus.eu/statistics/v1";
const DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions";
const DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro";
const AI_TIMEOUT_MS = 25_000;
const ANALYSIS_VERSION = "deepseek-v1";
const CACHE_SECONDS = 21_600;
const MAX_AREA_HECTARES = 2_500;

const NDVI_EVALSCRIPT = `//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  const invalidScl = [0, 1, 2, 3, 8, 9, 10, 11].includes(sample.SCL);
  const denominator = sample.B08 + sample.B04;
  const valid = sample.dataMask === 1 && !invalidScl && denominator !== 0;
  return {
    ndvi: [valid ? (sample.B08 - sample.B04) / denominator : 0],
    dataMask: [valid ? 1 : 0]
  };
}`;

class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export default {
  async fetch(request, env, context): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return json({
        status: "ok",
        services: {
          cdse: Boolean(env.CDSE_CLIENT_ID && env.CDSE_CLIENT_SECRET),
          ai: Boolean(env.DEEPSEEK_API_KEY),
        },
        aiProvider: "DeepSeek",
        aiModel: deepSeekModel(env),
      });
    }

    if (url.pathname === "/api/analyze") {
      if (request.method !== "POST") {
        return json({ error: "Metodo non consentito" }, 405, { Allow: "POST" });
      }
      try {
        return await analyze(request, env, context);
      } catch (error) {
        const status = error instanceof ApiError ? error.status : 500;
        const message = error instanceof Error ? error.message : "Errore imprevisto durante l'analisi";
        console.error("analysis_failed", { status, message });
        return json({ error: message }, status);
      }
    }

    if (url.pathname.startsWith("/api/")) {
      return json({ error: "Endpoint non trovato" }, 404);
    }

    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

async function analyze(request: Request, env: Env, context: ExecutionContext): Promise<Response> {
  if (!env.CDSE_CLIENT_ID || !env.CDSE_CLIENT_SECRET) {
    throw new ApiError(503, "Credenziali CDSE non configurate nel runtime");
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (contentLength > 64_000) {
    throw new ApiError(413, "Geometria troppo grande");
  }

  const body = await readAnalyzeRequest(request);
  const geometry = normalizePolygon(body.geometry);
  const areaHectares = geodesicAreaHectares(geometry.coordinates[0]);
  if (areaHectares < 0.01) {
    throw new ApiError(400, "Il campo deve avere una superficie di almeno 0,01 ha");
  }
  if (areaHectares > MAX_AREA_HECTARES) {
    throw new ApiError(400, `Il pilot online accetta al massimo ${MAX_AREA_HECTARES.toLocaleString("it-IT")} ha`);
  }

  const endDate = parseDate(body.endDate) ?? daysAgo(3);
  const startDate = parseDate(body.startDate) ?? shiftYear(endDate, -1);
  if (startDate >= endDate) {
    throw new ApiError(400, "L'intervallo temporale non e' valido");
  }

  const cacheId = await digest(JSON.stringify({
    version: ANALYSIS_VERSION,
    aiModel: deepSeekModel(env),
    geometry,
    startDate,
    endDate,
  }));
  const cacheKey = new Request(`https://analysis-cache.verdimetria/${cacheId}`);
  const cache = defaultCache();
  const cached = await cache.match(cacheKey);
  if (cached) {
    const response = new Response(cached.body, cached);
    response.headers.set("X-Verdimetria-Cache", "HIT");
    return response;
  }

  const centroid = polygonCentroid(geometry.coordinates[0]);
  const projection = projectToLocalUtm(geometry, centroid);
  const resolutionMeters = areaHectares > 500 ? 20 : 10;
  const token = await fetchCdseToken(env);

  const [catalogPayload, statisticalPayload] = await Promise.all([
    fetchProviderJson(
      CATALOG_URL,
      token,
      buildCatalogRequest(geometry, startDate, endDate),
      "application/geo+json",
    ),
    fetchProviderJson(
      STATISTICAL_URL,
      token,
      buildStatisticalRequest(
        projection.geometry,
        projection.epsg,
        startDate,
        endDate,
        resolutionMeters,
      ),
    ),
  ]);

  const catalog = parseCatalog(catalogPayload);
  const points = parseStatistics(statisticalPayload);
  if (points.length === 0) {
    throw new ApiError(422, "Nessuna osservazione NDVI valida nel periodo selezionato");
  }

  const vegetation = summarizeVegetation(points);
  const ai = await generateInsights(env, {
    areaHectares,
    startDate,
    endDate,
    catalog,
    vegetation,
  });

  const payload = {
    status: "ready",
    analysisId: cacheId.slice(0, 16),
    generatedAt: new Date().toISOString(),
    period: { from: startDate, to: endDate },
    area: {
      hectares: round(areaHectares, 2),
      centroid,
      utmCrs: `EPSG:${projection.epsg}`,
      resolutionMeters,
    },
    catalog,
    vegetation,
    ai,
    provenance: [
      {
        provider: "Copernicus Data Space Ecosystem",
        dataset: "Sentinel-2 L2A",
        services: ["Catalog API", "Statistical API"],
        quality: "SCL cloud/shadow mask + dataMask",
      },
      {
        provider: ai.provider,
        dataset: ai.model,
        services: ["Interpretazione strutturata"],
        quality: "Solo metriche aggregate; nessuna prescrizione automatica",
      },
    ],
    disclaimer:
      "Analisi osservativa da satellite: evidenzia pattern da verificare sul campo e non sostituisce sopralluogo, laboratorio o consulenza agronomica.",
  };

  const response = json(payload, 200, { "X-Verdimetria-Cache": "MISS" });
  const cacheResponse = new Response(response.clone().body, response);
  cacheResponse.headers.set("Cache-Control", `public, max-age=${CACHE_SECONDS}`);
  context.waitUntil(cache.put(cacheKey, cacheResponse));
  return response;
}

async function readAnalyzeRequest(request: Request): Promise<AnalyzeRequest> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    throw new ApiError(400, "Payload JSON non valido");
  }
  if (!isRecord(body) || !isRecord(body.geometry)) {
    throw new ApiError(400, "La geometria Polygon e' obbligatoria");
  }
  return body as unknown as AnalyzeRequest;
}

function normalizePolygon(value: PolygonGeometry): PolygonGeometry {
  if (value.type !== "Polygon" || !Array.isArray(value.coordinates) || value.coordinates.length === 0) {
    throw new ApiError(400, "Sono accettate solo geometrie Polygon");
  }

  let totalPoints = 0;
  const coordinates = value.coordinates.map((rawRing) => {
    if (!Array.isArray(rawRing) || rawRing.length < 3) {
      throw new ApiError(400, "Ogni anello del Polygon deve avere almeno tre vertici");
    }
    const ring = rawRing.map((rawPosition) => {
      if (!Array.isArray(rawPosition) || rawPosition.length < 2) {
        throw new ApiError(400, "Coordinata Polygon non valida");
      }
      const longitude = Number(rawPosition[0]);
      const latitude = Number(rawPosition[1]);
      if (
        !Number.isFinite(longitude) ||
        !Number.isFinite(latitude) ||
        longitude < -180 ||
        longitude > 180 ||
        latitude < -90 ||
        latitude > 90
      ) {
        throw new ApiError(400, "Coordinate fuori dai limiti WGS84");
      }
      totalPoints += 1;
      return [longitude, latitude] as Position;
    });
    const first = ring[0];
    const last = ring.at(-1);
    if (first[0] !== last?.[0] || first[1] !== last[1]) {
      ring.push([...first] as Position);
    }
    return ring;
  });

  if (totalPoints > 500) {
    throw new ApiError(400, "Il Polygon supera il limite di 500 vertici");
  }
  return { type: "Polygon", coordinates };
}

function buildCatalogRequest(
  geometry: PolygonGeometry,
  startDate: string,
  endDate: string,
): Record<string, unknown> {
  return {
    datetime: `${startDate}T00:00:00Z/${endDate}T23:59:59Z`,
    collections: ["sentinel-2-l2a"],
    limit: 100,
    intersects: geometry,
    filter: {
      op: "<=",
      args: [{ property: "eo:cloud_cover" }, 30],
    },
    "filter-lang": "cql2-json",
    fields: {
      include: [
        "collection",
        "properties.datetime",
        "properties.eo:cloud_cover",
        "properties.platform",
      ],
    },
  };
}

function buildStatisticalRequest(
  geometry: PolygonGeometry,
  epsg: number,
  startDate: string,
  endDate: string,
  resolutionMeters: number,
): Record<string, unknown> {
  return {
    input: {
      bounds: {
        geometry,
        properties: { crs: `http://www.opengis.net/def/crs/EPSG/0/${epsg}` },
      },
      data: [
        {
          type: "sentinel-2-l2a",
          dataFilter: { mosaickingOrder: "leastCC", maxCloudCoverage: 30 },
        },
      ],
    },
    aggregation: {
      timeRange: {
        from: `${startDate}T00:00:00Z`,
        to: `${endDate}T23:59:59Z`,
      },
      aggregationInterval: { of: "P10D", lastIntervalBehavior: "SHORTEN" },
      evalscript: NDVI_EVALSCRIPT,
      resx: resolutionMeters,
      resy: resolutionMeters,
    },
    calculations: {
      ndvi: {
        statistics: {
          default: { percentiles: { k: [10, 50, 90] } },
        },
      },
    },
  };
}

async function fetchCdseToken(env: Env): Promise<string> {
  const body = new URLSearchParams({
    grant_type: "client_credentials",
    client_id: env.CDSE_CLIENT_ID,
    client_secret: env.CDSE_CLIENT_SECRET,
  });
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) {
    throw new ApiError(502, `Autenticazione CDSE non riuscita (${response.status})`);
  }
  const payload: unknown = await response.json();
  if (!isRecord(payload) || typeof payload.access_token !== "string") {
    throw new ApiError(502, "Token CDSE non valido");
  }
  return payload.access_token;
}

async function fetchProviderJson(
  url: string,
  token: string,
  body: Record<string, unknown>,
  accept = "application/json",
): Promise<unknown> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: accept,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(45_000),
  });
  if (!response.ok) {
    const requestId = response.headers.get("x-request-id");
    throw new ApiError(
      502,
      `Provider CDSE non disponibile (${response.status}${requestId ? `, request ${requestId}` : ""})`,
    );
  }
  return response.json();
}

function parseCatalog(payload: unknown) {
  const rawFeatures = isRecord(payload) && Array.isArray(payload.features) ? payload.features : [];
  const items = rawFeatures
    .flatMap((feature) => {
      if (!isRecord(feature) || !isRecord(feature.properties)) return [];
      const acquiredAt = feature.properties.datetime;
      if (typeof acquiredAt !== "string") return [];
      const rawCloudCover = feature.properties["eo:cloud_cover"];
      return [{
        id: typeof feature.id === "string" ? feature.id : "scene",
        acquiredAt,
        cloudCover: typeof rawCloudCover === "number" ? round(rawCloudCover, 1) : null,
      }];
    })
    .sort((left, right) => right.acquiredAt.localeCompare(left.acquiredAt));

  const cloudValues = items.flatMap((item) => (item.cloudCover === null ? [] : [item.cloudCover]));
  return {
    sceneCount: items.length,
    latestAcquisition: items[0]?.acquiredAt ?? null,
    meanCloudCover: cloudValues.length > 0 ? round(average(cloudValues), 1) : null,
    items: items.slice(0, 12),
  };
}

function parseStatistics(payload: unknown): StatisticalPoint[] {
  const rawData = isRecord(payload) && Array.isArray(payload.data) ? payload.data : [];
  return rawData.flatMap((entry) => {
    if (!isRecord(entry) || !isRecord(entry.interval) || !isRecord(entry.outputs)) return [];
    const ndvi = entry.outputs.ndvi;
    if (!isRecord(ndvi) || !isRecord(ndvi.bands) || !isRecord(ndvi.bands.B0)) return [];
    const stats = ndvi.bands.B0.stats;
    if (!isRecord(stats)) return [];

    const from = entry.interval.from;
    const to = entry.interval.to;
    const mean = numberValue(stats.mean);
    const min = numberValue(stats.min);
    const max = numberValue(stats.max);
    const stDev = numberValue(stats.stDev);
    const sampleCount = numberValue(stats.sampleCount) ?? 0;
    const noDataCount = numberValue(stats.noDataCount) ?? 0;
    if (
      typeof from !== "string" ||
      typeof to !== "string" ||
      mean === null ||
      min === null ||
      max === null ||
      stDev === null ||
      sampleCount - noDataCount <= 0
    ) {
      return [];
    }

    const percentiles = isRecord(stats.percentiles) ? stats.percentiles : {};
    return [{
      date: to.slice(0, 10),
      from,
      to,
      mean: round(mean, 4),
      min: round(min, 4),
      max: round(max, 4),
      stDev: round(stDev, 4),
      p10: percentileValue(percentiles, 10),
      p50: percentileValue(percentiles, 50),
      p90: percentileValue(percentiles, 90),
      validPixels: Math.max(0, Math.round(sampleCount - noDataCount)),
    }];
  });
}

function summarizeVegetation(points: StatisticalPoint[]) {
  const means = points.map((point) => point.mean);
  const recent = means.slice(-3);
  const previous = means.slice(-6, -3);
  const trend = previous.length > 0 ? round(average(recent) - average(previous), 4) : null;
  return {
    points,
    current: means.at(-1) ?? null,
    average: round(average(means), 4),
    min: Math.min(...means),
    max: Math.max(...means),
    trend,
    validObservations: points.length,
    totalValidPixels: points.reduce((sum, point) => sum + point.validPixels, 0),
  };
}

async function generateInsights(
  env: Env,
  metrics: {
    areaHectares: number;
    startDate: string;
    endDate: string;
    catalog: ReturnType<typeof parseCatalog>;
    vegetation: ReturnType<typeof summarizeVegetation>;
  },
) {
  const fallback = ruleBasedInsights(metrics);
  try {
    if (!env.DEEPSEEK_API_KEY) {
      throw new Error("DeepSeek non configurato");
    }
    const model = deepSeekModel(env);
    const modelInput = {
      areaHectares: round(metrics.areaHectares, 2),
      period: { from: metrics.startDate, to: metrics.endDate },
      catalog: {
        sceneCount: metrics.catalog.sceneCount,
        latestAcquisition: metrics.catalog.latestAcquisition,
        meanCloudCover: metrics.catalog.meanCloudCover,
      },
      vegetation: {
        current: metrics.vegetation.current,
        average: metrics.vegetation.average,
        min: metrics.vegetation.min,
        max: metrics.vegetation.max,
        trend: metrics.vegetation.trend,
        validObservations: metrics.vegetation.validObservations,
        observations: metrics.vegetation.points.map((point) => ({
          date: point.date,
          mean: point.mean,
          stDev: point.stDev,
          p10: point.p10,
          p90: point.p90,
        })),
      },
    };
    const response = await fetch(DEEPSEEK_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.DEEPSEEK_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        thinking: { type: "disabled" },
      messages: [
        {
          role: "system",
          content:
            "Sei un assistente di interpretazione agronomica prudente. Usa solo i dati forniti, senza inventare unita', pendenze, cause o valori. Non diagnosticare carenze NPK o malattie e non dare prescrizioni. Restituisci esattamente JSON con summary (massimo 220 caratteri) e 3 insights. Ogni insight deve avere tone (solo alert, warn, ok o info), title (massimo 60 caratteri), text (massimo 240 caratteri) ed evidence (massimo 160 caratteri). Scrivi in italiano e suggerisci solo verifiche sul campo.",
        },
        {
          role: "user",
          content: JSON.stringify(modelInput),
        },
      ],
      response_format: { type: "json_object" },
      temperature: 0.2,
        max_tokens: 1_200,
      }),
      signal: AbortSignal.timeout(AI_TIMEOUT_MS),
    });
    const result: unknown = await response.json();
    if (!response.ok) {
      throw new Error(`DeepSeek HTTP ${response.status}`);
    }
    const content = extractAiContent(result);
    const parsed = content ? parseAiContent(content) : null;
    if (!parsed) throw new Error("Output AI non strutturato");
    return {
      provider: "DeepSeek",
      model,
      status: "generated",
      summary: parsed.summary,
      insights: parsed.insights,
    };
  } catch (error) {
    console.warn("ai_fallback", error instanceof Error ? error.message : "unknown");
    return {
      provider: "Verdimetria rules",
      model: "evidence-rules-v1",
      status: "fallback",
      summary: "Interpretazione automatica basata sulle metriche disponibili; il modello AI non ha risposto.",
      insights: fallback,
    };
  }
}

function deepSeekModel(env: Env): string {
  return env.DEEPSEEK_MODEL?.trim() || DEFAULT_DEEPSEEK_MODEL;
}

function ruleBasedInsights(metrics: {
  catalog: ReturnType<typeof parseCatalog>;
  vegetation: ReturnType<typeof summarizeVegetation>;
}): Insight[] {
  const { catalog, vegetation } = metrics;
  const current = vegetation.current ?? 0;
  const currentTone: Insight["tone"] = current >= 0.5 ? "ok" : current >= 0.3 ? "info" : "warn";
  const trend = vegetation.trend;
  return [
    {
      tone: catalog.sceneCount >= 4 ? "ok" : "warn",
      title: "Copertura osservativa",
      text:
        catalog.sceneCount >= 4
          ? "Il periodo contiene piu' acquisizioni utilizzabili per un confronto temporale."
          : "Le scene utili sono poche: interpretare il trend con cautela.",
      evidence: `${catalog.sceneCount} scene con cloud cover <= 30%; ${vegetation.validObservations} intervalli NDVI validi.`,
    },
    {
      tone: currentTone,
      title: "Stato dell'ultima osservazione",
      text:
        current >= 0.5
          ? "L'ultimo NDVI medio e' compatibile con copertura vegetale consistente."
          : current >= 0.3
            ? "L'ultimo NDVI medio indica copertura intermedia o una fase di transizione."
            : "L'ultimo NDVI medio e' basso: verificare fase colturale, suolo esposto e condizioni locali.",
      evidence: `NDVI medio ultimo intervallo ${round(current, 3)}; media periodo ${vegetation.average}.`,
    },
    {
      tone: trend !== null && trend < -0.08 ? "alert" : "info",
      title: "Variazione recente",
      text:
        trend === null
          ? "Non ci sono ancora abbastanza intervalli per confrontare due finestre recenti."
          : trend < -0.08
            ? "La media recente e' scesa rispetto alla finestra precedente: pianificare un controllo visivo delle zone interessate."
            : trend > 0.08
              ? "La media recente e' aumentata; confrontare il segnale con ciclo colturale e interventi registrati."
              : "La media recente e' sostanzialmente stabile rispetto alla finestra precedente.",
      evidence: trend === null ? "Trend non calcolabile." : `Delta NDVI tra finestre: ${trend > 0 ? "+" : ""}${trend}.`,
    },
  ];
}

function extractAiContent(result: unknown): string | null {
  if (!isRecord(result)) return null;
  if (typeof result.response === "string") return result.response;
  if (!Array.isArray(result.choices) || result.choices.length === 0) return null;
  const firstChoice = result.choices[0];
  if (!isRecord(firstChoice) || !isRecord(firstChoice.message)) return null;
  return typeof firstChoice.message.content === "string" ? firstChoice.message.content : null;
}

function parseAiContent(content: string): { summary: string; insights: Insight[] } | null {
  const normalized = content.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  const objectStart = normalized.indexOf("{");
  const objectEnd = normalized.lastIndexOf("}");
  if (objectStart < 0 || objectEnd <= objectStart) return null;
  let value: unknown;
  try {
    value = JSON.parse(normalized.slice(objectStart, objectEnd + 1));
  } catch {
    return null;
  }
  if (!isRecord(value) || typeof value.summary !== "string" || !Array.isArray(value.insights)) {
    return null;
  }
  const insights = value.insights.flatMap((item) => {
    const tone = isRecord(item) ? normalizeInsightTone(item.tone) : null;
    if (
      !isRecord(item) ||
      tone === null ||
      typeof item.title !== "string" ||
      typeof item.text !== "string" ||
      typeof item.evidence !== "string"
    ) {
      return [];
    }
    return [{
      tone,
      title: item.title.slice(0, 100),
      text: item.text.slice(0, 600),
      evidence: item.evidence.slice(0, 300),
    }];
  });
  return insights.length > 0 ? { summary: value.summary.slice(0, 500), insights: insights.slice(0, 5) } : null;
}

function normalizeInsightTone(value: unknown): Insight["tone"] | null {
  const aliases: Record<string, Insight["tone"]> = {
    alert: "alert",
    critical: "alert",
    danger: "alert",
    warn: "warn",
    warning: "warn",
    caution: "warn",
    ok: "ok",
    positive: "ok",
    good: "ok",
    info: "info",
    neutral: "info",
  };
  return typeof value === "string" ? aliases[value.toLowerCase()] ?? null : null;
}

function projectToLocalUtm(geometry: PolygonGeometry, centroid: Position) {
  const zone = Math.min(60, Math.max(1, Math.floor((centroid[0] + 180) / 6) + 1));
  const south = centroid[1] < 0;
  const epsg = (south ? 32_700 : 32_600) + zone;
  const target = `+proj=utm +zone=${zone} ${south ? "+south" : ""} +datum=WGS84 +units=m +no_defs`;
  const source = "+proj=longlat +datum=WGS84 +no_defs";
  return {
    epsg,
    geometry: {
      type: "Polygon" as const,
      coordinates: geometry.coordinates.map((ring) =>
        ring.map((position) => {
          const projected = proj4(source, target, position);
          return [projected[0], projected[1]] as Position;
        }),
      ),
    },
  };
}

function polygonCentroid(ring: Position[]): Position {
  const positions = ring.slice(0, -1);
  return [
    round(positions.reduce((sum, position) => sum + position[0], 0) / positions.length, 6),
    round(positions.reduce((sum, position) => sum + position[1], 0) / positions.length, 6),
  ];
}

function geodesicAreaHectares(ring: Position[]): number {
  const earthRadius = 6_378_137;
  let area = 0;
  for (let current = 0, previous = ring.length - 1; current < ring.length; previous = current++) {
    const [currentLongitude, currentLatitude] = ring[current];
    const [previousLongitude, previousLatitude] = ring[previous];
    area +=
      toRadians(currentLongitude - previousLongitude) *
      (2 + Math.sin(toRadians(previousLatitude)) + Math.sin(toRadians(currentLatitude)));
  }
  return Math.abs(area * earthRadius * earthRadius) / 2 / 10_000;
}

function toRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function parseDate(value: string | undefined): string | null {
  if (value === undefined) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) {
    throw new ApiError(400, "Le date devono avere formato YYYY-MM-DD");
  }
  return value;
}

function daysAgo(days: number): string {
  const date = new Date(Date.now() - days * 86_400_000);
  return date.toISOString().slice(0, 10);
}

function shiftYear(value: string, years: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCFullYear(date.getUTCFullYear() + years);
  return date.toISOString().slice(0, 10);
}

async function digest(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function percentileValue(percentiles: Record<string, unknown>, percentile: number): number | null {
  for (const key of [String(percentile), `${percentile}.0`]) {
    const value = numberValue(percentiles[key]);
    if (value !== null) return round(value, 4);
  }
  return null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function defaultCache(): Cache {
  return (caches as unknown as { default: Cache }).default;
}

function json(
  body: unknown,
  status = 200,
  extraHeaders: Record<string, string> = {},
): Response {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}