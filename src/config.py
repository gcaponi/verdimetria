"""
Configurazione centrale del progetto.

L'area di interesse (AOI) di default copre il territorio del libero consorzio
di Ragusa. Sono coordinate approssimative del bounding box provinciale
(WGS84, EPSG:4326) — vanno raffinate con un confine reale (es. shapefile
ISTAT dei confini amministrativi) prima di un uso serio.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AOI:
    """Bounding box dell'area di interesse in WGS84 (lon/lat)."""
    name: str
    west: float
    south: float
    east: float
    north: float

    def as_bbox(self) -> list[float]:
        """Formato [west, south, east, north], usato dalla maggior parte delle API STAC/OGC."""
        return [self.west, self.south, self.east, self.north]

    def as_geojson_polygon(self) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [[
                [self.west, self.south],
                [self.east, self.south],
                [self.east, self.north],
                [self.west, self.north],
                [self.west, self.south],
            ]],
        }


# Bounding box approssimativo del territorio della provincia di Ragusa.
# Sostituiscilo con un confine amministrativo reale (es. ISTAT) per un progetto serio:
# https://www.istat.it/it/archivio/222527 (confini delle unità amministrative)
RAGUSA_AOI = AOI(name="Ragusa", west=14.28, south=36.65, east=14.95, north=37.10)

# CRS di lavoro consigliato per analisi raster locali (proiettato, in metri).
# UTM zone 33N copre la Sicilia orientale.
WORKING_CRS = "EPSG:32633"

# Risoluzione target di default per lo stack raster (in metri, dato il CRS proiettato sopra).
DEFAULT_RESOLUTION_M = 30

# Percorsi di lavoro
DATA_DIR = "data"
RAW_DIR = f"{DATA_DIR}/raw"
PROCESSED_DIR = f"{DATA_DIR}/processed"
OUTPUTS_DIR = "outputs"
