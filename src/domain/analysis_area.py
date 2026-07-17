"""Area utente validata per analisi geospaziali riproducibili."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, TypeAlias

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform
from shapely.validation import explain_validity

GeoJsonGeometry: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RasterDimensions:
    width: int
    height: int

    @property
    def pixel_count(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class AnalysisArea:
    """Polygon o MultiPolygon WGS84 scelto dall'utente."""

    name: str
    geometry: Polygon | MultiPolygon

    @classmethod
    def from_geojson(cls, name: str, geometry: GeoJsonGeometry) -> AnalysisArea:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("AnalysisArea richiede un nome")

        geometry_type = geometry.get("type")
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("AnalysisArea accetta solo Polygon o MultiPolygon")

        parsed_geometry = shape(geometry)
        if not isinstance(parsed_geometry, (Polygon, MultiPolygon)):
            raise ValueError("La geometria GeoJSON non e' un Polygon o MultiPolygon")
        if parsed_geometry.is_empty:
            raise ValueError("La geometria non puo' essere vuota")
        if not parsed_geometry.is_valid:
            reason = explain_validity(parsed_geometry)
            raise ValueError(f"Geometria non valida: {reason}")

        west, south, east, north = parsed_geometry.bounds
        if west < -180 or east > 180 or south < -90 or north > 90:
            raise ValueError("Le coordinate devono essere WGS84 lon/lat")

        return cls(name=normalized_name, geometry=parsed_geometry)

    def to_geojson(self) -> GeoJsonGeometry:
        return mapping(self.geometry)

    def projected_geometry(self, target_crs: str) -> Polygon | MultiPolygon:
        transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
        projected = transform(transformer.transform, self.geometry)
        return projected

    def area_hectares(self, target_crs: str) -> float:
        return self.projected_geometry(target_crs).area / 10_000

    def raster_dimensions(
        self,
        resolution_m: float,
        target_crs: str,
        max_pixels: int = 25_000_000,
    ) -> RasterDimensions:
        if resolution_m <= 0:
            raise ValueError("La risoluzione deve essere maggiore di zero")
        if max_pixels <= 0:
            raise ValueError("Il budget pixel deve essere maggiore di zero")

        west, south, east, north = self.projected_geometry(target_crs).bounds
        dimensions = RasterDimensions(
            width=max(1, ceil((east - west) / resolution_m)),
            height=max(1, ceil((north - south) / resolution_m)),
        )
        if dimensions.pixel_count > max_pixels:
            raise ValueError(
                f"Area oltre budget: {dimensions.pixel_count} pixel richiesti, "
                f"massimo {max_pixels}"
            )
        return dimensions