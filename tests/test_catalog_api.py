from typing import Any

import pytest
from shapely.geometry import shape

from src.domain import AnalysisArea
from src.ingestion import catalog_api
from src.ingestion.catalog_api import build_catalog_request, parse_catalog_response

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


def catalog_feature(item_id: str, acquired_at: str, cloud_cover: float) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "geometry": FIELD_POLYGON,
        "properties": {
            "datetime": acquired_at,
            "eo:cloud_cover": cloud_cover,
        },
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeOAuthSession:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = iter(payloads)
        self.requests: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> FakeResponse:
        self.requests.append({"url": url, "json": dict(json), "headers": headers})
        return FakeResponse(next(self.payloads))


def test_build_catalog_request_uses_polygon_and_cloud_filter() -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)

    request_body = build_catalog_request(
        area,
        "2026-05-01",
        "2026-07-16",
        max_cloud_cover=15,
        limit=25,
    )

    assert shape(request_body["intersects"]).equals(area.geometry)
    assert request_body["datetime"] == "2026-05-01T00:00:00Z/2026-07-16T23:59:59Z"
    assert request_body["collections"] == ["sentinel-2-l2a"]
    assert request_body["filter"] == {
        "op": "<=",
        "args": [{"property": "eo:cloud_cover"}, 15],
    }
    assert request_body["filter-lang"] == "cql2-json"
    assert request_body["limit"] == 25
    assert "collection" in request_body["fields"]["include"]


def test_parse_catalog_response_returns_typed_items() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [catalog_feature("S2-item", "2026-07-10T10:00:00Z", 4.5)],
    }

    items = parse_catalog_response(payload)

    assert len(items) == 1
    assert items[0].item_id == "S2-item"
    assert items[0].acquired_at == "2026-07-10T10:00:00Z"
    assert items[0].cloud_cover == 4.5
    assert items[0].geometry == FIELD_POLYGON


def test_fetch_catalog_items_follows_pagination_and_total_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)
    fake_oauth = FakeOAuthSession([
        {
            "features": [catalog_feature("item-1", "2026-07-01T10:00:00Z", 2)],
            "context": {"next": 1},
        },
        {
            "features": [catalog_feature("item-2", "2026-07-11T10:00:00Z", 3)],
            "context": {},
        },
    ])
    monkeypatch.setattr(catalog_api, "get_oauth_session", lambda: fake_oauth)

    items = catalog_api.fetch_catalog_items(
        area,
        "2026-07-01",
        "2026-07-15",
        page_size=1,
        max_items=2,
    )

    assert [item.item_id for item in items] == ["item-1", "item-2"]
    assert len(fake_oauth.requests) == 2
    assert "next" not in fake_oauth.requests[0]["json"]
    assert fake_oauth.requests[1]["json"]["next"] == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_cloud_cover": 101}, "nuvolosa"),
        ({"limit": 0}, "limite per pagina"),
        ({"start_date": "2026-07-16", "end_date": "2026-07-01"}, "temporale"),
    ],
)
def test_build_catalog_request_rejects_invalid_options(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    area = AnalysisArea.from_geojson("Campo Vittoria", FIELD_POLYGON)
    defaults = {"start_date": "2026-07-01", "end_date": "2026-07-16"}
    defaults.update(kwargs)

    with pytest.raises(ValueError, match=message):
        build_catalog_request(area, **defaults)