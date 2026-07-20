import json
from decimal import Decimal

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import transaction
from django.db.models import Max

from backend.fields.models import BoundaryVersion, Field
from src.domain import AnalysisArea


def _postgis_geometry(area: AnalysisArea) -> MultiPolygon:
    geometry = GEOSGeometry(json.dumps(area.to_geojson()), srid=4326)
    if geometry.geom_type == "Polygon":
        return MultiPolygon(geometry, srid=4326)
    if not isinstance(geometry, MultiPolygon):
        raise ValueError("Il confine deve essere un Polygon o MultiPolygon")
    return geometry


@transaction.atomic
def append_boundary(
    field: Field,
    area: AnalysisArea,
    source: str = BoundaryVersion.Source.DRAW,
) -> BoundaryVersion:
    locked_field = Field.objects.select_for_update().get(pk=field.pk)
    last_version = locked_field.boundaries.aggregate(max_version=Max("version"))["max_version"]
    metric_crs = area.local_utm_crs()
    area_hectares = Decimal(str(area.area_hectares(metric_crs))).quantize(Decimal("0.0001"))
    return BoundaryVersion.objects.create(
        field=locked_field,
        version=(last_version or 0) + 1,
        geometry=_postgis_geometry(area),
        area_hectares=area_hectares,
        metric_crs=metric_crs,
        source=source,
    )