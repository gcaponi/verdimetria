from typing import Any

import pytest

from src.domain import AnalysisArea
from src.ingestion import ispra_lithology
from src.ingestion.ispra_lithology import (
    ISPRA_LAYER,
    ISPRA_WFS_URL,
    build_lithology_request,
    parse_lithology_response,
)

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


def feature(
    feature_id: str,
    geometry: dict[str, Any],
    **properties: Any,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": geometry,
        "properties": properties,
    }


class FakeResponse:
    headers = {"Content-Type": "application/json; charset=UTF-8"}

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict[str, Any], captured: dict[str, Any]) -> None:
        self.payload = payload
        self.captured = captured

    def get(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.captured.update(url=url, params=params, headers=headers, timeout=timeout)
        return FakeResponse(self.payload)


def test_build_lithology_request_uses_scoped_layer_and_crs84_bbox() -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)

    params = build_lithology_request(area, max_features=25)

    assert params == {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": ISPRA_LAYER,
        "outputFormat": "application/json",
        "srsName": "CRS:84",
        "bbox": "14.6,36.92,14.61,36.93,CRS:84",
        "count": 25,
    }


def test_parse_lithology_response_filters_bbox_false_positives() -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)
    distant_polygon = {
        "type": "Polygon",
        "coordinates": [[
            [14.70, 37.00],
            [14.71, 37.00],
            [14.71, 37.01],
            [14.70, 37.01],
            [14.70, 37.00],
        ]],
    }
    payload = {
        "type": "FeatureCollection",
        "features": [
            feature(
                "litologia100k.1",
                FIELD_POLYGON,
                cod_lito="A1",
                litologia="calcari",
                nome_ulf="calcare compatto",
                eta_geol="elveziano",
                classi_litologiche="calcareniti",
            ),
            feature("litologia100k.2", distant_polygon, litologia="arenarie"),
        ],
    }

    units = parse_lithology_response(area, payload)

    assert len(units) == 1
    assert units[0].feature_id == "litologia100k.1"
    assert units[0].code == "A1"
    assert units[0].lithology == "calcari"
    assert units[0].field_coverage == pytest.approx(1.0)
    assert units[0].overlap_hectares > 0


def test_fetch_lithology_context_calls_wfs_and_returns_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)
    captured: dict[str, Any] = {}

    payload = {
        "type": "FeatureCollection",
        "features": [feature("litologia100k.1", FIELD_POLYGON, litologia="calcari")],
    }
    fake_session = FakeSession(payload, captured)
    monkeypatch.setattr(ispra_lithology, "get_ispra_session", lambda: fake_session)

    units = ispra_lithology.fetch_lithology_context(area, timeout_seconds=12)

    assert captured["url"] == ISPRA_WFS_URL
    assert captured["params"]["srsName"] == "CRS:84"
    assert captured["headers"] == {"Accept": "application/geo+json, application/json"}
    assert captured["timeout"] == 12
    assert units[0].lithology == "calcari"


def test_lithology_request_rejects_invalid_limits() -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)

    with pytest.raises(ValueError, match="feature"):
        build_lithology_request(area, max_features=0)
    with pytest.raises(ValueError, match="timeout"):
        ispra_lithology.fetch_lithology_context(area, timeout_seconds=0)