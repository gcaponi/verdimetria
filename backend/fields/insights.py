"""Interpretazione AI delle metriche NDVI (port della logica del Worker V2).

Se DeepSeek non e' configurato (DEEPSEEK_API_KEY assente) o risponde male,
ritorna SEMPRE il fallback rule-based: mai eccezioni verso il chiamante.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
AI_TIMEOUT_SECONDS = 25

SYSTEM_PROMPT = (
    "Sei un assistente di interpretazione agronomica prudente. Usa solo i dati "
    "forniti, senza inventare unita', pendenze, cause o valori. Non diagnosticare "
    "carenze NPK o malattie e non dare prescrizioni. Restituisci esattamente JSON "
    "con summary (massimo 220 caratteri) e 3 insights. Ogni insight deve avere tone "
    "(solo alert, warn, ok o info), title (massimo 60 caratteri), text (massimo 240 "
    "caratteri) ed evidence (massimo 160 caratteri). Scrivi in italiano e suggerisci "
    "solo verifiche sul campo."
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


def rule_based_insights(catalog: dict[str, Any], vegetation: dict[str, Any]) -> list[dict[str, Any]]:
    current = vegetation.get("current") or 0
    if current >= 0.5:
        current_tone = "ok"
        current_text = "L'ultimo NDVI medio e' compatibile con copertura vegetale consistente."
    elif current >= 0.3:
        current_tone = "info"
        current_text = (
            "L'ultimo NDVI medio indica copertura intermedia o una fase di transizione."
        )
    else:
        current_tone = "warn"
        current_text = (
            "L'ultimo NDVI medio e' basso: verificare fase colturale, "
            "suolo esposto e condizioni locali."
        )

    scene_count = catalog.get("sceneCount", 0)
    trend = vegetation.get("trend")
    if trend is None:
        trend_tone = "info"
        trend_text = "Non ci sono ancora abbastanza intervalli per confrontare due finestre recenti."
        trend_evidence = "Trend non calcolabile."
    elif trend < -0.08:
        trend_tone = "alert"
        trend_text = (
            "La media recente e' scesa rispetto alla finestra precedente: "
            "pianificare un controllo visivo delle zone interessate."
        )
        trend_evidence = f"Delta NDVI tra finestre: {trend}."
    elif trend > 0.08:
        trend_tone = "info"
        trend_text = (
            "La media recente e' aumentata; confrontare il segnale con ciclo "
            "colturale e interventi registrati."
        )
        trend_evidence = f"Delta NDVI tra finestre: +{trend}."
    else:
        trend_tone = "info"
        trend_text = "La media recente e' sostanzialmente stabile rispetto alla finestra precedente."
        trend_evidence = f"Delta NDVI tra finestre: {trend}."

    return [
        {
            "tone": "ok" if scene_count >= 4 else "warn",
            "title": "Copertura osservativa",
            "text": (
                "Il periodo contiene piu' acquisizioni utilizzabili per un confronto temporale."
                if scene_count >= 4
                else "Le scene utili sono poche: interpretare il trend con cautela."
            ),
            "evidence": (
                f"{scene_count} scene con cloud cover <= 30%; "
                f"{vegetation.get('validObservations', 0)} intervalli NDVI validi."
            ),
        },
        {
            "tone": current_tone,
            "title": "Stato dell'ultima osservazione",
            "text": current_text,
            "evidence": (
                f"NDVI medio ultimo intervallo {round(current, 3)}; "
                f"media periodo {vegetation.get('average', 0)}."
            ),
        },
        {
            "tone": trend_tone,
            "title": "Variazione recente",
            "text": trend_text,
            "evidence": trend_evidence,
        },
    ]


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
    return {"summary": value["summary"][:500], "insights": insights[:5]}


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


def _fallback_result(insights: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "Verdimetria rules",
        "model": "evidence-rules-v1",
        "status": "fallback",
        "summary": FALLBACK_SUMMARY,
        "insights": insights,
    }


def generate_insights(metrics: dict[str, Any]) -> dict[str, Any]:
    """Genera il blocco `ai` del contratto FieldAnalysis. Mai eccezioni."""
    fallback = _fallback_result(
        rule_based_insights(metrics["catalog"], metrics["vegetation"])
    )
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return fallback

    model = deepseek_model()
    model_input = {
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
                "max_tokens": 1200,
            },
            timeout=AI_TIMEOUT_SECONDS,
        )
        if not response.ok:
            raise ValueError(f"DeepSeek HTTP {response.status_code}")
        content = _extract_ai_content(response.json())
        parsed = parse_ai_content(content) if content else None
        if parsed is None:
            raise ValueError("Output AI non strutturato")
        return {
            "provider": "DeepSeek",
            "model": model,
            "status": "generated",
            "summary": parsed["summary"],
            "insights": parsed["insights"],
        }
    except Exception as error:
        logger.warning("ai_fallback: %s", error)
        return fallback
