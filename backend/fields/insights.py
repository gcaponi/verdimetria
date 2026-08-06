"""Interpretazione AI delle metriche di campo (port della logica del Worker V2).

Il prompt modella un ingegnere agronomo prudente: diagnosi dello stato del
campo, possibili cause solo come ipotesi da verificare sul campo, azioni
pratiche prioritarie e cosa monitorare. Se DeepSeek non e' configurato
(DEEPSEEK_API_KEY assente) o risponde male, ritorna SEMPRE il fallback
rule-based costruito sugli stessi dati: mai eccezioni verso il chiamante.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
AI_TIMEOUT_SECONDS = 25

# Prezzi DeepSeek in EUR per 1M token, coppia (input, output).
# Fonte: listino DeepSeek fornito dal progetto (2026-08); modelli non
# presenti ricadono sul prezzo di DEFAULT_DEEPSEEK_MODEL con un warning.
AI_PRICING_EUR_PER_MILLION = {
    "deepseek-v4-pro": (Decimal("2.24"), Decimal("2.24")),
    "deepseek-v4-flash": (Decimal("0.14"), Decimal("0.28")),
}

MAX_AI_INSIGHTS = 6

SYSTEM_PROMPT = (
    "Sei un ingegnere agronomo che interpreta i dati satellitari Sentinel-2 di "
    "un campo agricolo. Scrivi in italiano una valutazione agronomica prudente "
    "usando SOLO i dati forniti: non inventare valori, unita', meteo o cause. "
    "Vincoli non negoziabili: non diagnosticare mai malattie, patogeni o carenze "
    "N-P-K specifiche; ogni possibile causa va presentata come ipotesi da "
    "verificare sul campo; declaredCrop e reportedInterventions sono riferiti "
    "dall'utente e non verificati: usali solo come contesto; ogni insight deve "
    "citare in evidence i valori numerici che lo sostengono. "
    "Restituisci esattamente JSON con: summary (2-3 frasi, max 400 caratteri) "
    "che collega vegetazione (NDVI), umidita' (NDMI), stagione e coltura "
    "dichiarata; e insights (4-6 elementi). Ogni insight ha: tone (solo alert, "
    "warn, ok o info); title (max 80 caratteri) che inizia con 'Diagnosi:', "
    "'Da verificare:', 'Azione consigliata:' o 'Monitoraggio:'; text (max 400 "
    "caratteri); evidence (max 200 caratteri) con i numeri rilevanti. "
    "Gli insights devono coprire: le possibili cause del pattern osservato "
    "(collega trend NDVI, NDMI, variabilita' del campo, pendenza/esposizione, "
    "copertura del suolo, coltura dichiarata e interventi registrati) come "
    "ipotesi da verificare; azioni pratiche prioritarie per l'agricoltore "
    "(sopralluogo mirato nelle zone deboli, controllo dell'irrigazione, "
    "campionamento del suolo dove indicato); cosa monitorare nelle prossime "
    "settimane."
)

FALLBACK_SUMMARY = (
    "Interpretazione automatica basata sulle metriche disponibili; "
    "il modello AI non ha risposto."
)

TONE_ALIASES = {
    "alert": "alert",
    "critical": "alert",
    "danger": "alert",
    "warn": "warn",
    "warning": "warn",
    "caution": "warn",
    "ok": "ok",
    "positive": "ok",
    "good": "ok",
    "info": "info",
    "neutral": "info",
}


def deepseek_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "").strip() or DEFAULT_DEEPSEEK_MODEL


def deepseek_url() -> str:
    base = os.getenv("DEEPSEEK_BASE_URL", "").strip() or DEFAULT_DEEPSEEK_BASE_URL
    return f"{base.rstrip('/')}/chat/completions"


def rule_based_insights(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Fallback rule-based: diagnosi agronomica prudente dagli stessi dati."""
    catalog = metrics["catalog"]
    vegetation = metrics["vegetation"]
    ndmi = metrics.get("ndmi") or {}
    variability = metrics.get("variability") or {}
    terrain = metrics.get("terrain") or {}
    interventions = metrics.get("interventions") or []
    crop = str(metrics.get("crop") or "").strip()

    current = vegetation.get("current") or 0
    trend = vegetation.get("trend")
    ndmi_current = ndmi.get("current")
    ndmi_trend = ndmi.get("trend")
    weak_share = variability.get("weak")
    scene_count = catalog.get("sceneCount", 0)

    if current >= 0.5:
        diagnosis_tone = "ok"
        diagnosis_state = "copertura vegetale consistente"
    elif current >= 0.3:
        diagnosis_tone = "info"
        diagnosis_state = "copertura intermedia o fase di transizione"
    else:
        diagnosis_tone = "warn"
        diagnosis_state = "copertura bassa (suolo esposto o inizio/fine ciclo)"
    if trend is None:
        trend_clause = "senza abbastanza intervalli per confrontare due finestre recenti"
    elif trend < -0.08:
        trend_clause = f"in calo rispetto alla finestra precedente (delta {trend})"
    elif trend > 0.08:
        trend_clause = f"in aumento rispetto alla finestra precedente (delta +{trend})"
    else:
        trend_clause = f"sostanzialmente stabile (delta {trend})"
    crop_clause = (
        f" Contesto: {crop} (coltura dichiarata dall'utente, non verificata)."
        if crop
        else ""
    )

    insights: list[dict[str, Any]] = [
        {
            "tone": diagnosis_tone,
            "title": "Diagnosi: stato della vegetazione",
            "text": (
                f"L'ultimo NDVI medio indica {diagnosis_state}, {trend_clause}."
                f"{crop_clause}"
            ),
            "evidence": (
                f"NDVI medio ultimo intervallo {round(current, 3)}; "
                f"media periodo {vegetation.get('average', 0)}; "
                f"delta finestre {trend if trend is not None else 'n.d.'}."
            ),
        }
    ]

    hypotheses: list[dict[str, Any]] = []
    if trend is not None and trend < -0.08:
        if ndmi_trend is not None and ndmi_trend < 0:
            hypotheses.append({
                "tone": "alert",
                "title": "Da verificare: possibile stress idrico",
                "text": (
                    "NDVI e umidita' (NDMI) in calo insieme sono compatibili con "
                    "stress idrico, ma anche con avanzamento del ciclo o "
                    "interventi recenti: ipotesi da verificare sul campo."
                ),
                "evidence": (
                    f"Delta NDVI {trend}; delta NDMI {ndmi_trend}; "
                    f"NDMI ultimo {ndmi_current}."
                ),
            })
        else:
            hypotheses.append({
                "tone": "alert",
                "title": "Da verificare: calo recente del vigore",
                "text": (
                    "La media recente e' scesa rispetto alla finestra precedente: "
                    "le possibili cause (idriche, colturali, sanitarie) sono solo "
                    "ipotesi da verificare con un controllo visivo delle zone "
                    "interessate."
                ),
                "evidence": (
                    f"Delta NDVI tra finestre: {trend}; delta NDMI "
                    f"{ndmi_trend if ndmi_trend is not None else 'n.d.'}."
                ),
            })
    if weak_share is not None and weak_share >= 20:
        hypotheses.append({
            "tone": "warn",
            "title": "Da verificare: zone a basso vigore estese",
            "text": (
                f"Circa il {weak_share}% del campo risulta a vigore debole: "
                "possibili cause locali (compattamento, ristagno, emergenza "
                "irregolare) da verificare con un sopralluogo mirato."
            ),
            "evidence": (
                f"Classe debole (NDVI < 0.3): {weak_share}% dei pixel validi il "
                f"{variability.get('date')} (soglie convenzionali MVP)."
            ),
        })
    slope = terrain.get("slope") or {}
    slope_mean = slope.get("mean")
    if slope_mean is not None and slope_mean >= 8:
        hypotheses.append({
            "tone": "info",
            "title": "Da verificare: pendenza e deflusso",
            "text": (
                "La pendenza media non e' trascurabile: nelle zone in pendenza "
                "verificare deflusso e disponibilita' idrica differenziata "
                "rispetto alle zone piane."
            ),
            "evidence": (
                f"Pendenza media {slope_mean} gradi (max {slope.get('max')}); "
                f"esposizione dominante {terrain.get('aspectDominant') or 'n.d.'}."
            ),
        })
    insights.extend(hypotheses[:2])

    actions: list[dict[str, Any]] = []
    if weak_share is not None and weak_share >= 20:
        actions.append({
            "tone": "warn",
            "title": "Azione consigliata: sopralluogo mirato",
            "text": (
                "Sopralluogo nelle zone a vigore debole per verificare le "
                "possibili cause; se il pattern persiste, valutare un "
                "campionamento del suolo da inviare a laboratorio."
            ),
            "evidence": (
                f"Classe debole {weak_share}% dei pixel validi il "
                f"{variability.get('date')}."
            ),
        })
    if (ndmi_current is not None and ndmi_current < 0.2) or (
        ndmi_trend is not None and ndmi_trend < -0.05
    ):
        actions.append({
            "tone": "warn",
            "title": "Azione consigliata: controllo irrigazione",
            "text": (
                "L'umidita' vegetale risulta bassa o in calo: verificare il "
                "funzionamento dell'impianto e l'uniformita' di distribuzione."
            ),
            "evidence": f"NDMI ultimo {ndmi_current}; delta NDMI {ndmi_trend}.",
        })
    if not actions:
        actions.append({
            "tone": "info",
            "title": "Azione consigliata: verifica di routine",
            "text": (
                "Nessuna anomalia evidente nei dati: confermare il quadro "
                "satellitare con un sopralluogo di routine prima di qualunque "
                "intervento."
            ),
            "evidence": (
                f"NDVI medio ultimo intervallo {round(current, 3)}; "
                f"{vegetation.get('validObservations', 0)} intervalli NDVI validi."
            ),
        })
    insights.extend(actions)

    if scene_count >= 4:
        monitoring_tone = "info"
        monitoring_text = "Confrontare le prossime acquisizioni con lo stato attuale"
    else:
        monitoring_tone = "warn"
        monitoring_text = (
            "Le scene utili sono poche: interpretare il trend con cautela e "
            "attendere nuove acquisizioni"
        )
    if interventions:
        latest = interventions[0]
        monitoring_text += (
            f"; incrociare il segnale con l'ultimo intervento riportato "
            f"({latest.get('label') or latest.get('kind')} del "
            f"{latest.get('date')}, riferito dall'utente)"
        )
    monitoring_text += "."
    insights.append({
        "tone": monitoring_tone,
        "title": "Monitoraggio: prossime settimane",
        "text": monitoring_text,
        "evidence": (
            f"{scene_count} scene utili nel periodo; "
            f"{vegetation.get('validObservations', 0)} intervalli NDVI validi."
        ),
    })

    return insights[:MAX_AI_INSIGHTS]


def _normalize_tone(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return TONE_ALIASES.get(value.lower())


def parse_ai_content(content: str) -> dict[str, Any] | None:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.removeprefix("```json").removeprefix("```").strip()
    if normalized.endswith("```"):
        normalized = normalized[: -3].strip()
    object_start = normalized.find("{")
    object_end = normalized.rfind("}")
    if object_start < 0 or object_end <= object_start:
        return None
    try:
        value = json.loads(normalized[object_start : object_end + 1])
    except ValueError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("summary"), str):
        return None
    raw_insights = value.get("insights")
    if not isinstance(raw_insights, list):
        return None

    insights: list[dict[str, Any]] = []
    for item in raw_insights:
        if not isinstance(item, dict):
            continue
        tone = _normalize_tone(item.get("tone"))
        title = item.get("title")
        text = item.get("text")
        evidence = item.get("evidence")
        if (
            tone is None
            or not isinstance(title, str)
            or not isinstance(text, str)
            or not isinstance(evidence, str)
        ):
            continue
        insights.append({
            "tone": tone,
            "title": title[:100],
            "text": text[:600],
            "evidence": evidence[:300],
        })
    if not insights:
        return None
    return {"summary": value["summary"][:500], "insights": insights[:MAX_AI_INSIGHTS]}


def _extract_ai_content(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("response"), str):
        return payload["response"]
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
        return None
    content = first["message"].get("content")
    return content if isinstance(content, str) else None


def _extract_ai_usage(payload: Any, model: str) -> dict[str, Any]:
    """Usage token dalla risposta DeepSeek; zeri se il blocco `usage` manca."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {"tokens_in": 0, "tokens_out": 0, "model": model}
    return {
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "model": model,
    }


def compute_ai_cost_eur(tokens_in: int, tokens_out: int, model: str) -> Decimal:
    """Costo stimato della chiamata AI in EUR, quantizzato a 6 decimali."""
    pricing = AI_PRICING_EUR_PER_MILLION.get(model)
    if pricing is None:
        logger.warning(
            "ai_pricing_unknown_model: %s (uso il prezzo di %s)",
            model,
            DEFAULT_DEEPSEEK_MODEL,
        )
        pricing = AI_PRICING_EUR_PER_MILLION[DEFAULT_DEEPSEEK_MODEL]
    price_in, price_out = pricing
    cost = (
        Decimal(tokens_in) * price_in + Decimal(tokens_out) * price_out
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def _fallback_result(insights: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "Verdimetria rules",
        "model": "evidence-rules-v1",
        "status": "fallback",
        "summary": FALLBACK_SUMMARY,
        "insights": insights,
    }


def _build_model_input(metrics: dict[str, Any]) -> dict[str, Any]:
    """Contesto completo per il prompt: metriche derivate + diario interventi."""
    model_input: dict[str, Any] = {
        "areaHectares": round(metrics["areaHectares"], 2),
        "period": {"from": metrics["startDate"], "to": metrics["endDate"]},
        "catalog": {
            "sceneCount": metrics["catalog"]["sceneCount"],
            "latestAcquisition": metrics["catalog"]["latestAcquisition"],
            "meanCloudCover": metrics["catalog"]["meanCloudCover"],
        },
        "vegetation": {
            "current": metrics["vegetation"]["current"],
            "average": metrics["vegetation"]["average"],
            "min": metrics["vegetation"]["min"],
            "max": metrics["vegetation"]["max"],
            "trend": metrics["vegetation"]["trend"],
            "validObservations": metrics["vegetation"]["validObservations"],
            "observations": [
                {
                    "date": point["date"],
                    "mean": point["mean"],
                    "stDev": point["stDev"],
                    "p10": point["p10"],
                    "p90": point["p90"],
                }
                for point in metrics["vegetation"]["points"]
            ],
        },
    }
    crop = str(metrics.get("crop") or "").strip()
    if crop:
        # User-declared, optional and unverified: context for interpretation only.
        model_input["declaredCrop"] = (
            f"{crop} (coltura dichiarata dall'utente, opzionale e non verificata)"
        )
    ndmi = metrics.get("ndmi")
    if ndmi:
        model_input["ndmi"] = {
            "current": ndmi.get("current"),
            "average": ndmi.get("average"),
            "min": ndmi.get("min"),
            "max": ndmi.get("max"),
            "trend": ndmi.get("trend"),
            "validObservations": ndmi.get("validObservations"),
            "observations": [
                {"date": point["date"], "mean": point["mean"]}
                for point in ndmi.get("points", [])
            ],
        }
    variability = metrics.get("variability")
    if variability:
        model_input["variability"] = {
            "date": variability.get("date"),
            "weak": variability.get("weak"),
            "intermediate": variability.get("intermediate"),
            "vigorous": variability.get("vigorous"),
            "method": variability.get("method"),
            "note": (
                "Classi di vigore da soglie NDVI convenzionali MVP, "
                "non verita' agronomica."
            ),
        }
    terrain = metrics.get("terrain")
    if terrain:
        model_input["terrain"] = {
            "elevation": terrain.get("elevation"),
            "slope": terrain.get("slope"),
            "aspectDominant": terrain.get("aspectDominant"),
        }
    land_cover = metrics.get("landCover")
    if land_cover:
        model_input["landCover"] = {
            "year": land_cover.get("year"),
            "classes": [
                {
                    "label": item.get("label"),
                    "share": item.get("share"),
                    "hectares": item.get("hectares"),
                }
                for item in land_cover.get("classes", [])
            ],
            "note": (
                "CLC+ Backbone 2021: fotografia del 2021, non necessariamente "
                "aggiornata al periodo in analisi."
            ),
        }
    interventions = metrics.get("interventions") or []
    if interventions:
        # User-reported diary entries, most recent first: unverified context.
        model_input["reportedInterventions"] = [
            {
                "date": item.get("date"),
                "label": item.get("label") or item.get("kind"),
                "notes": item.get("notes") or "",
            }
            for item in interventions
        ]
    return model_input


def generate_insights(
    metrics: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Genera il blocco `ai` del contratto FieldAnalysis. Mai eccezioni.

    Ritorna (blocco_ai, usage): usage e' {"tokens_in", "tokens_out", "model"}
    solo se DeepSeek ha risposto con output valido, None per il fallback
    rule-based (chiave assente, errore HTTP o output non strutturato).
    """
    fallback = _fallback_result(rule_based_insights(metrics))
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return fallback, None

    model = deepseek_model()
    model_input = _build_model_input(metrics)
    try:
        response = requests.post(
            deepseek_url(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "thinking": {"type": "disabled"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(model_input)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": 1600,
            },
            timeout=AI_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise ValueError(f"DeepSeek HTTP {response.status_code}")
        payload = response.json()
        content = _extract_ai_content(payload)
        parsed = parse_ai_content(content) if content else None
        if parsed is None:
            raise ValueError("Output AI non strutturato")
        return {
            "provider": "DeepSeek",
            "model": model,
            "status": "generated",
            "summary": parsed["summary"],
            "insights": parsed["insights"],
        }, _extract_ai_usage(payload, model)
    except Exception as error:
        logger.warning("ai_fallback: %s", error)
        return fallback, None
