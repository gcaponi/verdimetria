"""Live smoke for production provider credentials.

Each function calls the shipped integration (CDSE catalog, DeepSeek insights,
Brevo via send_ops_alert, Stripe Account.retrieve, public probes). Used after
a Finestra C rotation and by `manage.py smoke_providers`.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import stripe
from django.conf import settings
from django.core.management import call_command

from backend.fields.insights import generate_insights
from src.domain import AnalysisArea
from src.ingestion.catalog_api import fetch_catalog_items
from src.ingestion.process_api import get_oauth_session

DEFAULT_PROBE_URLS = {
    "health": "https://api.verdimetria.cais.uno/health/",
    "ready": "https://api.verdimetria.cais.uno/ready/",
}

SMOKE_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.61, 36.92],
        [14.61, 36.93],
        [14.60, 36.93],
        [14.60, 36.92],
    ]],
}

SMOKE_METRICS: dict[str, Any] = {
    "areaHectares": 2.64,
    "startDate": "2026-05-01",
    "endDate": "2026-07-31",
    "catalog": {
        "sceneCount": 6,
        "latestAcquisition": "2026-07-25T09:30:00Z",
        "meanCloudCover": 12.3,
    },
    "vegetation": {
        "current": 0.38,
        "average": 0.44,
        "min": 0.38,
        "max": 0.52,
        "trend": -0.11,
        "validObservations": 6,
        "points": [
            {"date": "2026-07-06", "mean": 0.45, "stDev": 0.07, "p10": 0.3, "p90": 0.6},
            {"date": "2026-07-11", "mean": 0.38, "stDev": 0.09, "p10": 0.2, "p90": 0.55},
        ],
    },
    "ndmi": {
        "current": 0.16,
        "average": 0.24,
        "min": 0.16,
        "max": 0.31,
        "trend": -0.08,
        "validObservations": 6,
        "points": [
            {"date": "2026-07-06", "mean": 0.24},
            {"date": "2026-07-11", "mean": 0.16},
        ],
    },
    "variability": {
        "date": "2026-07-11",
        "weak": 32.0,
        "intermediate": 41.0,
        "vigorous": 27.0,
        "method": "histogram",
    },
}


def smoke_health(
    health_url: str = DEFAULT_PROBE_URLS["health"],
    ready_url: str = DEFAULT_PROBE_URLS["ready"],
    timeout: float = 8.0,
) -> dict[str, Any]:
    """GET /health/ and /ready/ must be HTTP 200 with a sane JSON body."""
    health = _get_json(health_url, timeout=timeout)
    ready = _get_json(ready_url, timeout=timeout)
    if health.get("status") != "ok":
        raise RuntimeError("health probe body is not ok")
    if ready.get("status") != "ready":
        raise RuntimeError("ready probe body is not ready")
    return {"health": health, "ready": ready}


def smoke_cdse() -> dict[str, Any]:
    """OAuth token + Catalog search on the shipped CDSE client."""
    session = get_oauth_session()
    area = AnalysisArea.from_geojson("finestra-c-smoke", SMOKE_POLYGON)
    items = fetch_catalog_items(
        area,
        "2026-06-01",
        "2026-07-15",
        oauth=session,
        max_items=3,
        page_size=3,
    )
    if not items:
        raise RuntimeError("CDSE catalog returned no scenes")
    return {"scenes": len(items), "latest": items[0].item_id}


def smoke_deepseek() -> dict[str, Any]:
    """Live structured completion through generate_insights."""
    block, usage = generate_insights(SMOKE_METRICS)
    if block.get("status") != "generated" or usage is None:
        raise RuntimeError("DeepSeek fell back to rule-based output")
    return {
        "status": block["status"],
        "model": usage.get("model"),
        "insights": len(block.get("insights") or []),
    }


def smoke_brevo() -> dict[str, Any]:
    """Send the allowlisted operational test mail through the shipped command."""
    call_command("send_ops_alert", "test")
    return {"event": "test", "accepted": True}


def smoke_stripe() -> dict[str, Any]:
    """Authenticated Stripe API ping. No checkout, no customer mutation."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    if not settings.STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY is empty")
    account = stripe.Account.retrieve()
    account_id = getattr(account, "id", None) or account.get("id")
    if not account_id:
        raise RuntimeError("Stripe Account.retrieve returned no id")
    return {"account_id": str(account_id)}


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        raise RuntimeError(f"{url} returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"{url} unreachable") from error
    if status != 200:
        raise RuntimeError(f"{url} returned HTTP {status}")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} body is not a JSON object")
    return payload
