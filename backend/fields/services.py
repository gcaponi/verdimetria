import json
from decimal import Decimal

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import transaction
from django.db.models import Max

from backend.fields.models import BoundaryVersion, Field
from src.domain import AnalysisArea

# Copertura operativa dichiarata: Italia continentale, Sicilia, Sardegna (bbox).
# Approssimazione esplicita: include piccole aree di mare/confine; il rifiuto
# preciso fuori Italia arriva comunque dopo (TINITALY/CLC+ non hanno tile li').
ITALY_MIN_LON, ITALY_MAX_LON = 6.6, 18.9
ITALY_MIN_LAT, ITALY_MAX_LAT = 35.3, 47.3


def ensure_italy_coverage(area: AnalysisArea) -> None:
    """Rifiuta campi il cui baricentro cade fuori dalla copertura operativa."""
    centroid = area.geometry.centroid
    if not (
        ITALY_MIN_LON <= centroid.x <= ITALY_MAX_LON
        and ITALY_MIN_LAT <= centroid.y <= ITALY_MAX_LAT
    ):
        raise ValueError(
            "Il campo e' fuori dalla copertura operativa: al momento analizziamo solo campi in Italia"
        )


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
    ensure_italy_coverage(area)
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