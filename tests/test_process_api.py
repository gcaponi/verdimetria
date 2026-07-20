from pathlib import Path
from typing import Any

import pytest

from src.domain import AnalysisArea
from src.ingestion import process_api
from src.ingestion.process_api import NDVI_RAW_EVALSCRIPT, build_process_request


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

PIEDMONT_FIELD_POLYGON: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [7.67, 45.06],
        [7.68, 45.06],
        [7.68, 45.07],
        [7.67, 45.07],
        [7.67, 45.06],
    ]],
}


class FakeResponse:
    content = b"fake-geotiff"

    def raise_for_status(self) -> None:
        return None


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


def test_build_process_request_uses_projected_geometry_and_metric_dimensions() -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    request_body = build_process_request(
        NDVI_RAW_EVALSCRIPT,
        area,
        "2026-06-01",
        "2026-06-30",
        target_crs="EPSG:32633",
        resolution_m=10,
    )

    bounds = request_body["input"]["bounds"]
    dimensions = area.raster_dimensions(10, "EPSG:32633")

    assert "bbox" not in bounds
    assert bounds["geometry"]["type"] == "Polygon"
    assert bounds["properties"]["crs"] == "http://www.opengis.net/def/crs/EPSG/0/32633"
    assert request_body["output"]["width"] == dimensions.width
    assert request_body["output"]["height"] == dimensions.height
    assert request_body["input"]["data"][0]["dataFilter"] == {
        "timeRange": {
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-06-30T23:59:59Z",
        },
        "maxCloudCoverage": 20,
    }


def test_ndvi_evalscript_masks_invalid_scl_and_data_pixels() -> None:
    assert '"SCL"' in NDVI_RAW_EVALSCRIPT
    assert '"dataMask"' in NDVI_RAW_EVALSCRIPT
    assert "return [NaN]" in NDVI_RAW_EVALSCRIPT


def test_process_request_selects_local_utm_when_crs_is_omitted() -> None:
    area = AnalysisArea.from_geojson("Campo Piemonte", PIEDMONT_FIELD_POLYGON)

    request_body = build_process_request(
        NDVI_RAW_EVALSCRIPT,
        area,
        "2026-06-01",
        "2026-06-30",
    )

    assert request_body["input"]["bounds"]["properties"]["crs"].endswith("/32632")


def test_fetch_ndvi_posts_built_payload_and_writes_geotiff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)
    fake_oauth = FakeOAuthSession()
    output_path = tmp_path / "ndvi.tiff"
    monkeypatch.setattr(process_api, "get_oauth_session", lambda: fake_oauth)

    process_api.fetch_ndvi(
        area,
        "2026-06-01",
        "2026-06-30",
        str(output_path),
        resolution_m=20,
    )

    assert fake_oauth.url == process_api.PROCESS_URL
    assert fake_oauth.headers == {"Accept": "image/tiff"}
    assert fake_oauth.request_body is not None
    assert "geometry" in fake_oauth.request_body["input"]["bounds"]
    assert output_path.read_bytes() == b"fake-geotiff"


@pytest.mark.parametrize(
    ("start_date", "end_date", "max_cloud_cover", "message"),
    [
        ("2026-06-30", "2026-06-01", 20, "intervallo temporale"),
        ("2026-06-01", "2026-06-30", -1, "copertura nuvolosa"),
        ("2026-06-01", "2026-06-30", 101, "copertura nuvolosa"),
    ],
)
def test_build_process_request_rejects_invalid_filters(
    start_date: str,
    end_date: str,
    max_cloud_cover: int,
    message: str,
) -> None:
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    with pytest.raises(ValueError, match=message):
        build_process_request(
            NDVI_RAW_EVALSCRIPT,
            area,
            start_date,
            end_date,
            max_cloud_cover=max_cloud_cover,
        )