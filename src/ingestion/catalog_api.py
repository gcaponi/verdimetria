"""Ricerca acquisizioni CDSE tramite Sentinel Hub Catalog API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from src.domain import AnalysisArea
from src.domain.analysis_area import GeoJsonGeometry
from src.ingestion.process_api import get_oauth_session

CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"


@dataclass(frozen=True, slots=True)
class CatalogItem:
    item_id: str
    acquired_at: str
    cloud_cover: float | None
    collection: str
    geometry: GeoJsonGeometry


def build_catalog_request(
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    *,
    collection: str = "sentinel-2-l2a",
    max_cloud_cover: int = 20,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as error:
        raise ValueError("Le date devono avere formato YYYY-MM-DD") from error

    if start > end:
        raise ValueError("L'intervallo temporale non e' valido")
    if not collection:
        raise ValueError("La collezione non puo' essere vuota")
    if not 0 <= max_cloud_cover <= 100:
        raise ValueError("La copertura nuvolosa deve essere compresa tra 0 e 100")
    if not 1 <= limit <= 100:
        raise ValueError("Il limite per pagina deve essere compreso tra 1 e 100")

    return {
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "collections": [collection],
        "limit": limit,
        "intersects": area.to_geojson(),
        "filter": {
            "op": "<=",
            "args": [{"property": "eo:cloud_cover"}, max_cloud_cover],
        },
        "filter-lang": "cql2-json",
        "fields": {
            "include": [
                "collection",
                "properties.eo:cloud_cover",
                "properties.platform",
            ]
        },
    }


def parse_catalog_response(payload: dict[str, Any]) -> list[CatalogItem]:
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError("La Catalog API ha restituito un payload STAC non valido")

    items: list[CatalogItem] = []
    for raw_feature in raw_features:
        if not isinstance(raw_feature, dict):
            continue
        properties = raw_feature.get("properties")
        geometry = raw_feature.get("geometry")
        item_id = raw_feature.get("id")
        collection = raw_feature.get("collection")
        if (
            not isinstance(properties, dict)
            or not isinstance(geometry, dict)
            or not isinstance(item_id, str)
            or not isinstance(collection, str)
        ):
            continue
        acquired_at = properties.get("datetime")
        if not isinstance(acquired_at, str):
            continue
        raw_cloud_cover = properties.get("eo:cloud_cover")
        cloud_cover = (
            float(raw_cloud_cover)
            if isinstance(raw_cloud_cover, (int, float)) and not isinstance(raw_cloud_cover, bool)
            else None
        )
        items.append(
            CatalogItem(
                item_id=item_id,
                acquired_at=acquired_at,
                cloud_cover=cloud_cover,
                collection=collection,
                geometry=cast(GeoJsonGeometry, geometry),
            )
        )
    return items


def fetch_catalog_items(
    area: AnalysisArea,
    start_date: str,
    end_date: str,
    *,
    collection: str = "sentinel-2-l2a",
    max_cloud_cover: int = 20,
    page_size: int = 100,
    max_items: int = 500,
) -> list[CatalogItem]:
    if max_items <= 0:
        raise ValueError("Il limite totale deve essere maggiore di zero")

    request_body = build_catalog_request(
        area,
        start_date,
        end_date,
        collection=collection,
        max_cloud_cover=max_cloud_cover,
        limit=min(page_size, max_items),
    )
    oauth = get_oauth_session()
    items: list[CatalogItem] = []

    while True:
        response = oauth.post(
            CATALOG_URL,
            json=request_body,
            headers={"Accept": "application/geo+json", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("La Catalog API ha restituito un payload STAC non valido")
        items.extend(parse_catalog_response(cast(dict[str, Any], payload)))
        if len(items) >= max_items:
            return items[:max_items]

        context = payload.get("context")
        next_token = context.get("next") if isinstance(context, dict) else None
        if next_token is None:
            return items
        request_body["next"] = next_token
        request_body["limit"] = min(page_size, max_items - len(items))