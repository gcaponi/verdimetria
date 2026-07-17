from typing import Any

import pytest

from src.domain import AnalysisArea
from src.ingestion import statistical_api
from src.ingestion.statistical_api import (
    NDVI_STATISTICS_EVALSCRIPT,
    build_statistical_request,
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


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"data": [], "status": "OK"}


class FakeOAuthSession:
    def __init__(self) -> None:
        self.url = ""
        self.request_body: dict[str, Any] | None = None
        self.headers: dict[str, str] | None = None

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> FakeResponse:
        self.url = url
        self.request_body = json
        self.headers = headers
        return FakeResponse()


def test_build_statistical_request_uses_masked_ndvi_and_projected_geometry() -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    request_body = build_statistical_request(
        NDVI_STATISTICS_EVALSCRIPT,
        area,
        "2026-06-01",
        "2026-06-30",
        aggregation_interval="P10D",
        resolution_m=20,
        percentiles=(10, 50, 90),
    )

    bounds = request_body["input"]["bounds"]
    assert bounds["geometry"]["type"] == "Polygon"
    assert bounds["properties"]["crs"] == "http://www.opengis.net/def/crs/EPSG/0/32633"
    assert request_body["input"]["data"][0]["dataFilter"] == {
        "mosaickingOrder": "leastCC",
        "maxCloudCoverage": 20,
    }
    assert request_body["aggregation"] == {
        "timeRange": {
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-06-30T23:59:59Z",
        },
        "aggregationInterval": {
            "of": "P10D",
            "lastIntervalBehavior": "SHORTEN",
        },
        "evalscript": NDVI_STATISTICS_EVALSCRIPT,
        "resx": 20,
        "resy": 20,
    }
    assert request_body["calculations"]["ndvi"]["statistics"] == {
        "default": {"percentiles": {"k": [10, 50, 90]}},
    }
    assert 'id: "dataMask"' in NDVI_STATISTICS_EVALSCRIPT
    assert "invalidScl" in NDVI_STATISTICS_EVALSCRIPT


def test_fetch_ndvi_statistics_posts_payload_and_returns_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)
    fake_oauth = FakeOAuthSession()
    monkeypatch.setattr(statistical_api, "get_oauth_session", lambda: fake_oauth)

    result = statistical_api.fetch_ndvi_statistics(
        area,
        "2026-06-01",
        "2026-06-30",
    )

    assert fake_oauth.url == statistical_api.STATISTICAL_URL
    assert fake_oauth.headers == {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    assert fake_oauth.request_body is not None
    assert result == {"data": [], "status": "OK"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_cloud_cover": 101}, "copertura nuvolosa"),
        ({"percentiles": (-1, 50)}, "percentili"),
        ({"last_interval_behavior": "INVALID"}, "ultimo intervallo"),
    ],
)
def test_build_statistical_request_rejects_invalid_options(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    with pytest.raises(ValueError, match=message):
        build_statistical_request(
            NDVI_STATISTICS_EVALSCRIPT,
            area,
            "2026-06-01",
            "2026-06-30",
            **kwargs,
        )