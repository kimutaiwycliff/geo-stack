"""Reusable bounding-box filter helpers for PostGIS and DuckDB queries."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @classmethod
    def from_string(cls, bbox_str: str) -> "BBox":
        """Parse 'xmin,ymin,xmax,ymax' string (EPSG:4326 coordinates)."""
        parts = [float(p.strip()) for p in bbox_str.split(",")]
        if len(parts) != 4:
            raise ValueError(f"bbox must have exactly 4 values, got {len(parts)}")
        xmin, ymin, xmax, ymax = parts
        if xmin >= xmax or ymin >= ymax:
            raise ValueError(f"Invalid bbox: min values must be less than max values")
        if not (-180 <= xmin <= 180 and -180 <= xmax <= 180):
            raise ValueError("Longitude values must be between -180 and 180")
        if not (-90 <= ymin <= 90 and -90 <= ymax <= 90):
            raise ValueError("Latitude values must be between -90 and 90")
        return cls(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)

    def to_wkt(self) -> str:
        return (
            f"POLYGON(({self.xmin} {self.ymin}, {self.xmax} {self.ymin}, "
            f"{self.xmax} {self.ymax}, {self.xmin} {self.ymax}, {self.xmin} {self.ymin}))"
        )

    def to_postgis_envelope(self) -> str:
        return f"ST_MakeEnvelope({self.xmin}, {self.ymin}, {self.xmax}, {self.ymax}, 4326)"

    def to_duckdb_filter(self, geom_col: str = "geometry") -> str:
        """DuckDB ST_Intersects filter expression using bbox columns if present."""
        return (
            f"ST_Intersects({geom_col}, "
            f"ST_GeomFromText('{self.to_wkt()}'))"
        )
