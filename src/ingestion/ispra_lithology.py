"""Contesto litologico ISPRA 1:100.000 tramite WFS pubblico."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, cast

import requests
from pyproj import Transformer
from requests.adapters import HTTPAdapter
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform

from src.domain import AnalysisArea

ISPRA_WFS_URL = "https://sgi2.isprambiente.it/geoserver/ge-core8/ows"
ISPRA_LAYER = "ge-core8:litologia100k"
ISPRA_DATASET_URL = (
    "https://www.isprambiente.gov.it/it/banche-dati/banche-dati-folder/"
    "suolo-e-territorio/cartografia-geologica-e-geotematica"
)
ISPRA_LICENSE_URL = "https://www.isprambiente.gov.it/it/copyright"
ISPRA_METADATA_URL = (
    "http://catalogosgi.isprambiente.it/geoportalAdm2/rest/document"
    "?id=ispra_rm%3AMeta_Geo_DT000002_RN"
)
ISPRA_SCALE_DENOMINATOR = 100_000


@dataclass(frozen=True, slots=True)
class LithologyUnit:
    feature_id: str
    code: str | None
    lithology: str | None
    formation_name: str | None
    geologic_age: str | None
    lithology_classes: str | None
    overlap_hectares: float
    field_coverage: float


class _ISPRAHttpAdapter(HTTPAdapter):
    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,
    ) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers("AES128-SHA")
        pool_kwargs["ssl_context"] = context
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def get_ispra_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://sgi2.isprambiente.it/", _ISPRAHttpAdapter())
    return session


def build_lithology_request(
    area: AnalysisArea,
    *,
    max_features: int = 1_000,
) -> dict[str, str | int]:
    if max_features <= 0:
        raise ValueError("Il numero massimo di feature deve essere maggiore di zero")

    west, south, east, north = area.geometry.bounds
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": ISPRA_LAYER,
        "outputFormat": "application/json",
        "srsName": "CRS:84",
        "bbox": f"{west},{south},{east},{north},CRS:84",
        "count": max_features,
    }


def parse_lithology_response(
    area: AnalysisArea,
    payload: dict[str, Any],
) -> list[LithologyUnit]:
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("Il WFS ISPRA ha restituito un payload GeoJSON non valido")

    metric_crs = area.local_utm_crs()
    field_hectares = area.area_hectares(metric_crs)
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    units: list[LithologyUnit] = []

    for raw_feature in raw_features:
        if not isinstance(raw_feature, dict):
            continue
        raw_geometry = raw_feature.get("geometry")
        properties = raw_feature.get("properties")
        if not isinstance(raw_geometry, dict) or not isinstance(properties, dict):
            continue

        provider_geometry = shape(raw_geometry)
        if not isinstance(provider_geometry, (Polygon, MultiPolygon)):
            continue
        overlap = area.geometry.intersection(provider_geometry)
        if overlap.is_empty or overlap.area == 0:
            continue

        overlap_hectares = transform(transformer.transform, overlap).area / 10_000
        units.append(
            LithologyUnit(
                feature_id=str(raw_feature.get("id", "")),
                code=_optional_string(properties, "cod_lito"),
                lithology=_optional_string(properties, "litologia"),
                formation_name=_optional_string(properties, "nome_ulf"),
                geologic_age=_optional_string(properties, "eta_geol"),
                lithology_classes=_optional_string(properties, "classi_litologiche"),
                overlap_hectares=overlap_hectares,
                field_coverage=min(1.0, overlap_hectares / field_hectares),
            )
        )

    return sorted(units, key=lambda unit: unit.overlap_hectares, reverse=True)


def fetch_lithology_context(
    area: AnalysisArea,
    *,
    timeout_seconds: float = 30,
    max_features: int = 1_000,
) -> list[LithologyUnit]:
    if timeout_seconds <= 0:
        raise ValueError("Il timeout deve essere maggiore di zero")

    response = get_ispra_session().get(
        ISPRA_WFS_URL,
        params=build_lithology_request(area, max_features=max_features),
        headers={"Accept": "application/geo+json, application/json"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "json" not in content_type:
        raise ValueError("Il WFS ISPRA non ha restituito GeoJSON")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Il WFS ISPRA ha restituito un payload GeoJSON non valido")
    return parse_lithology_response(area, cast(dict[str, Any], payload))


def _optional_string(properties: dict[str, Any], key: str) -> str | None:
    value = properties.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None