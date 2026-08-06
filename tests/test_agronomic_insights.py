"""AI Insights agronomici: contesto del prompt, schema invariato e fallback."""

import json
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pytest
from rest_framework.test import APIClient

from backend.accounts.models import User
from backend.fields.insights import (
    compute_ai_cost_eur,
    generate_insights,
    parse_ai_content,
    rule_based_insights,
)
from backend.fields.jobs import build_job_params, compute_idempotency_key
from backend.fields.models import AnalysisJob, Field, Intervention
from backend.fields.tasks import run_analysis_job
from src.ingestion.catalog_api import CatalogItem

FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [14.60, 36.92],
        [14.61, 36.92],
        [14.61, 36.93],
        [14.60, 36.93],
        [14.60, 36.92],
    ]],
}

AI_CONTENT: dict[str, Any] = {
    "summary": (
        "Campo in calo di vigore con umidita' in riduzione: quadro compatibile "
        "con stress idrico da verificare, nel contesto della coltura dichiarata."
    ),
    "insights": [
        {
            "tone": "warn",
            "title": "Diagnosi: vigore in calo",
            "text": "NDVI medio sotto la media del periodo e in calo tra le finestre recenti.",
            "evidence": "NDVI ultimo 0.38; media periodo 0.44; delta -0.11.",
        },
        {
            "tone": "alert",
            "title": "Da verificare: possibile stress idrico",
            "text": "NDVI e NDMI in calo insieme: ipotesi da verificare sul campo.",
            "evidence": "Delta NDVI -0.11; delta NDMI -0.08; NDMI ultimo 0.16.",
        },
        {
            "tone": "warn",
            "title": "Azione consigliata: controllo irrigazione",
            "text": "Verificare impianto e uniformita' di distribuzione nelle zone deboli.",
            "evidence": "NDMI ultimo 0.16; classe debole 32.0% dei pixel.",
        },
        {
            "tone": "info",
            "title": "Monitoraggio: prossime settimane",
            "text": "Confrontare le prossime acquisizioni con gli interventi riportati.",
            "evidence": "6 scene utili; 6 intervalli NDVI validi.",
        },
    ],
}


def _metrics(**overrides: Any) -> dict[str, Any]:
    metrics: dict[str, Any] = {
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
        "terrain": {
            "elevation": {"min": 10.0, "max": 25.0, "mean": 17.5},
            "slope": {"mean": 3.2, "max": 8.1},
            "aspectDominant": "SE",
        },
        "landCover": {
            "year": 2021,
            "classes": [
                {"label": "Erbacee periodiche (seminativi)", "share": 0.8, "hectares": 2.1}
            ],
        },
        "crop": "Grano duro",
        "interventions": [
            {
                "date": "2026-07-20",
                "kind": "irrigation",
                "label": "Irrigazione",
                "notes": "2 ore goccia a goccia",
            },
            {
                "date": "2026-06-15",
                "kind": "fertilization",
                "label": "Concimazione",
                "notes": "",
            },
        ],
    }
    metrics.update(overrides)
    return metrics


def _mock_deepseek(monkeypatch: pytest.MonkeyPatch, content: Any = AI_CONTENT) -> dict[str, Any]:
    """DeepSeek mockato: cattura la request e risponde con `content`."""
    captured: dict[str, Any] = {}
    content_str = json.dumps(content) if isinstance(content, (dict, list)) else content

    class _Response:
        ok = True

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": content_str}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 400},
            }

    def _post(url: str, headers: Any = None, json: Any = None, timeout: Any = None) -> Any:
        captured["url"] = url
        captured["request"] = json
        return _Response()

    monkeypatch.setattr("backend.fields.insights.requests.post", _post)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    return captured


def _request_payload(captured: dict[str, Any]) -> dict[str, Any]:
    return json.loads(captured["request"]["messages"][1]["content"])


def test_prompt_carries_full_agronomic_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _mock_deepseek(monkeypatch)

    result, _usage = generate_insights(_metrics())

    assert result["status"] == "generated"
    system_prompt = captured["request"]["messages"][0]["content"]
    assert "agronomo" in system_prompt
    payload = _request_payload(captured)
    assert payload["declaredCrop"].startswith("Grano duro")
    assert "non verificata" in payload["declaredCrop"]
    assert payload["reportedInterventions"][0]["label"] == "Irrigazione"
    assert payload["reportedInterventions"][0]["notes"] == "2 ore goccia a goccia"
    assert payload["ndmi"]["current"] == 0.16
    assert payload["ndmi"]["trend"] == -0.08
    assert payload["variability"]["weak"] == 32.0
    assert payload["terrain"]["slope"]["mean"] == 3.2
    assert payload["terrain"]["aspectDominant"] == "SE"
    assert "seminativi" in payload["landCover"]["classes"][0]["label"]


def test_generated_output_keeps_unchanged_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_deepseek(monkeypatch)

    result, usage = generate_insights(_metrics())

    assert set(result) == {"provider", "model", "status", "summary", "insights"}
    assert result["status"] == "generated"
    assert isinstance(result["summary"], str)
    assert result["insights"]
    for insight in result["insights"]:
        assert set(insight) == {"tone", "title", "text", "evidence"}
        assert insight["tone"] in {"alert", "warn", "ok", "info"}
        assert all(isinstance(insight[key], str) for key in ("title", "text", "evidence"))
    # Usage token riportata dal blocco `usage` della risposta DeepSeek.
    assert usage == {"tokens_in": 1200, "tokens_out": 400, "model": "deepseek-v4-pro"}


def test_prompt_omits_crop_and_interventions_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _mock_deepseek(monkeypatch)

    generate_insights(_metrics(crop="", interventions=[]))

    payload = _request_payload(captured)
    assert "declaredCrop" not in payload
    assert "reportedInterventions" not in payload


def test_fallback_produces_actionable_agronomic_insights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "backend.fields.insights.requests.post",
        Mock(side_effect=AssertionError("il fallback non deve chiamare DeepSeek")),
    )

    result, usage = generate_insights(_metrics())

    assert result["status"] == "fallback"
    assert usage is None  # chiave assente: nessuna chiamata, nessun costo
    assert set(result) == {"provider", "model", "status", "summary", "insights"}
    titles = [insight["title"] for insight in result["insights"]]
    assert any(title.startswith("Diagnosi:") for title in titles)
    assert any(title.startswith("Da verificare:") for title in titles)
    actions = [i for i in result["insights"] if i["title"].startswith("Azione consigliata:")]
    assert actions, "il fallback deve sempre proporre almeno un'azione"
    assert all(action["evidence"] for action in actions)
    assert any(title.startswith("Monitoraggio:") for title in titles)
    # Metriche in calo su NDVI+NDMI e 32% di campo debole: ipotesi e azioni attese.
    assert "Da verificare: possibile stress idrico" in titles
    assert "Azione consigliata: controllo irrigazione" in titles
    assert "Azione consigliata: sopralluogo mirato" in titles
    # Le cause restano ipotesi da verificare, mai diagnosi certe.
    for insight in result["insights"]:
        if insight["title"].startswith("Da verificare:"):
            assert "verificare" in insight["text"]
    # Coltura dichiarata e interventi citati come contesto riferito dall'utente.
    diagnosis = next(i for i in result["insights"] if i["title"].startswith("Diagnosi:"))
    assert "Grano duro" in diagnosis["text"]
    assert "non verificata" in diagnosis["text"]
    monitoring = next(i for i in result["insights"] if i["title"].startswith("Monitoraggio:"))
    assert "riferito dall'utente" in monitoring["text"]


def test_fallback_with_empty_crop_and_interventions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    calm_metrics = _metrics(
        crop="",
        interventions=[],
        vegetation={
            "current": 0.55,
            "average": 0.53,
            "min": 0.5,
            "max": 0.55,
            "trend": 0.02,
            "validObservations": 6,
            "points": [{"date": "2026-07-11", "mean": 0.55, "stDev": 0.05, "p10": 0.4, "p90": 0.65}],
        },
        ndmi={
            "current": 0.3,
            "average": 0.29,
            "min": 0.27,
            "max": 0.3,
            "trend": 0.01,
            "validObservations": 6,
            "points": [{"date": "2026-07-11", "mean": 0.3}],
        },
        variability={
            "date": "2026-07-11",
            "weak": 8.0,
            "intermediate": 32.0,
            "vigorous": 60.0,
            "method": "histogram",
        },
    )

    result, _usage = generate_insights(calm_metrics)

    assert result["status"] == "fallback"
    titles = [insight["title"] for insight in result["insights"]]
    assert "Azione consigliata: verifica di routine" in titles
    diagnosis = next(i for i in result["insights"] if i["title"].startswith("Diagnosi:"))
    assert "dichiarata" not in diagnosis["text"]
    monitoring = next(i for i in result["insights"] if i["title"].startswith("Monitoraggio:"))
    assert "intervento" not in monitoring["text"]


def test_invalid_ai_output_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_deepseek(monkeypatch, content="non e' JSON strutturato")

    result, usage = generate_insights(_metrics())

    assert result["status"] == "fallback"
    assert usage is None  # output non valido: niente usage, nessun costo tracciato
    assert result["insights"]  # il fallback rule-based resta completo


def test_ai_cost_uses_model_pricing() -> None:
    # v4-pro: prezzo unico 2.24 EUR/1M token (input e output).
    assert compute_ai_cost_eur(1000, 500, "deepseek-v4-pro") == Decimal("0.003360")
    # v4-flash: input 0.14 e output 0.28 EUR/1M token.
    assert compute_ai_cost_eur(1000, 500, "deepseek-v4-flash") == Decimal("0.000280")
    # Modello sconosciuto: prezzo di default v4-pro.
    assert compute_ai_cost_eur(1000, 500, "deepseek-futuro") == Decimal("0.003360")


def test_parse_ai_content_keeps_up_to_six_insights() -> None:
    content = {
        "summary": "Sintesi",
        "insights": [
            {"tone": "info", "title": f"Monitoraggio: {i}", "text": "t", "evidence": "e"}
            for i in range(7)
        ],
    }

    parsed = parse_ai_content(json.dumps(content))

    assert parsed is not None
    assert len(parsed["insights"]) == 6


def test_rule_based_insights_without_derived_blocks() -> None:
    minimal = _metrics(ndmi=None, variability=None, terrain=None, landCover=None, crop="")

    insights = rule_based_insights(minimal)

    titles = [insight["title"] for insight in insights]
    assert any(title.startswith("Diagnosi:") for title in titles)
    assert any(title.startswith("Azione consigliata:") for title in titles)
    assert any(title.startswith("Monitoraggio:") for title in titles)


# --- Task-level: il job passa blocchi derivati e diario a generate_insights ---

STATISTICAL_PAYLOAD: dict[str, Any] = {
    "data": [
        {
            "interval": {"from": "2026-07-01T00:00:00Z", "to": "2026-07-06T00:00:00Z"},
            "outputs": {
                "ndvi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.42,
                                "min": 0.1,
                                "max": 0.7,
                                "stDev": 0.08,
                                "sampleCount": 1000,
                                "noDataCount": 50,
                                "percentiles": {"10.0": 0.3, "50.0": 0.42, "90.0": 0.6},
                            }
                        }
                    }
                },
                "ndmi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.28,
                                "min": 0.1,
                                "max": 0.45,
                                "stDev": 0.06,
                                "sampleCount": 1000,
                                "noDataCount": 50,
                                "percentiles": {"10.0": 0.15, "50.0": 0.28, "90.0": 0.4},
                            }
                        }
                    }
                },
            },
        },
        {
            "interval": {"from": "2026-07-06T00:00:00Z", "to": "2026-07-11T00:00:00Z"},
            "outputs": {
                "ndvi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.45,
                                "min": 0.12,
                                "max": 0.72,
                                "stDev": 0.07,
                                "sampleCount": 1000,
                                "noDataCount": 40,
                            },
                            "histogram": {
                                "bins": [
                                    {"lowEdge": 0.2, "highEdge": 0.3, "count": 96},
                                    {"lowEdge": 0.3, "highEdge": 0.4, "count": 288},
                                    {"lowEdge": 0.5, "highEdge": 0.6, "count": 576},
                                ],
                                "underflowCount": 0,
                                "overflowCount": 0,
                            },
                        }
                    }
                },
                "ndmi": {
                    "bands": {
                        "B0": {
                            "stats": {
                                "mean": 0.31,
                                "min": 0.12,
                                "max": 0.48,
                                "stDev": 0.05,
                                "sampleCount": 1000,
                                "noDataCount": 40,
                            }
                        }
                    }
                },
            },
        },
    ]
}

CATALOG_ITEMS = [
    CatalogItem(
        item_id="S2A_20260710",
        acquired_at="2026-07-10T09:30:00Z",
        cloud_cover=5.0,
        collection="sentinel-2-l2a",
        geometry={"type": "Polygon", "coordinates": []},
    )
]

TERRAIN_RESULT: dict[str, Any] = {
    "elevation": {"min": 10.0, "max": 25.0, "mean": 17.5},
    "slope": {"mean": 3.2, "max": 8.1},
    "aspectDominant": "SE",
    "resolutionMeters": 30,
    "validPixels": 30,
}

AI_RESULT: dict[str, Any] = {
    "provider": "Verdimetria rules",
    "model": "evidence-rules-v1",
    "status": "fallback",
    "summary": "Sintesi di test",
    "insights": [],
}


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def field(api_client: APIClient, user: User) -> Field:
    api_client.force_authenticate(user)
    response = api_client.post(
        "/api/v1/fields/",
        {"name": "Campo agronomo", "boundary": FIELD_POLYGON},
        format="json",
    )
    assert response.status_code == 201
    return Field.objects.get(pk=response.data["id"])


@pytest.mark.django_db
def test_task_passes_derived_blocks_and_interventions_to_insights(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    field: Field,
) -> None:
    monkeypatch.setattr("backend.fields.tasks.get_oauth_session", lambda: Mock())
    monkeypatch.setattr(
        "backend.fields.tasks.fetch_catalog_items", lambda *a, **k: CATALOG_ITEMS
    )
    monkeypatch.setattr(
        "backend.fields.tasks.fetch_ndvi_statistics", lambda *a, **k: STATISTICAL_PAYLOAD
    )
    monkeypatch.setattr("backend.fields.tasks.fetch_dem", lambda *a, **k: b"dem")
    monkeypatch.setattr(
        "backend.fields.tasks.compute_morphometry", lambda *a, **k: TERRAIN_RESULT
    )
    captured: dict[str, Any] = {}

    def _capture(metrics: dict[str, Any]) -> tuple[dict[str, Any], None]:
        captured["metrics"] = metrics
        return AI_RESULT, None

    monkeypatch.setattr("backend.fields.tasks.generate_insights", _capture)
    field.crop = "Grano duro"
    field.save(update_fields=("crop",))
    for day in range(1, 13):  # 12 interventi: il contesto AI ne tiene al massimo 10
        Intervention.objects.create(
            field=field,
            owner=user,
            kind="irrigation" if day % 2 else "note",
            date=date(2026, 7, day),
            notes=f"nota {day}",
        )
    params = build_job_params(field)
    job = AnalysisJob.objects.create(
        field=field,
        owner=user,
        boundary_version=params["boundary_version"],
        idempotency_key=compute_idempotency_key(field, params),
        params=params,
    )

    run_analysis_job.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.result["ai"] == AI_RESULT
    metrics = captured["metrics"]
    assert metrics["crop"] == "Grano duro"
    assert metrics["ndmi"]["current"] == 0.31
    assert metrics["variability"]["weak"] == 10.0
    assert metrics["terrain"] == TERRAIN_RESULT
    assert metrics["landCover"] is None
    interventions = metrics["interventions"]
    assert len(interventions) == 10  # cap sulle voci piu' recenti
    assert interventions[0]["date"] == "2026-07-12"
    assert interventions[-1]["date"] == "2026-07-03"
    assert interventions[0]["kind"] == "note"
    assert interventions[0]["label"] == "Nota"
    assert interventions[0]["notes"] == "nota 12"
    # JSON-serializzabile: il risultato del job viene persistito in JSONField.
    json.dumps(metrics["interventions"])
