from typing import Any

import pytest

from src.domain import AnalysisArea


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


def test_analysis_area_preserves_polygon_and_computes_metric_values():
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    assert area.to_geojson()["type"] == "Polygon"
    assert area.area_hectares("EPSG:32633") > 0

    dimensions = area.raster_dimensions(10, "EPSG:32633")
    assert dimensions.width > 0
    assert dimensions.height > 0
    assert dimensions.pixel_count == dimensions.width * dimensions.height


def test_analysis_area_accepts_multipolygon():
    multipolygon: dict[str, Any] = {
        "type": "MultiPolygon",
        "coordinates": [FIELD_POLYGON["coordinates"]],
    }

    area = AnalysisArea.from_geojson("Due parcelle", multipolygon)

    assert area.to_geojson()["type"] == "MultiPolygon"


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"type": "Point", "coordinates": [14.60, 36.92]}, "Polygon o MultiPolygon"),
        (
            {
                "type": "Polygon",
                "coordinates": [[[14.60, 36.92], [14.61, 36.93], [14.61, 36.92], [14.60, 36.93], [14.60, 36.92]]],
            },
            "Geometria non valida",
        ),
    ],
)
def test_analysis_area_rejects_unsupported_or_invalid_geometry(
    geometry: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AnalysisArea.from_geojson("Campo", geometry)


def test_analysis_area_enforces_pixel_budget():
    area = AnalysisArea.from_geojson("Campo pilota", FIELD_POLYGON)

    with pytest.raises(ValueError, match="oltre budget"):
        area.raster_dimensions(10, "EPSG:32633", max_pixels=100)