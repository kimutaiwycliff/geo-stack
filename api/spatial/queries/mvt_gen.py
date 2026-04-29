"""ST_AsMVT query builder for PostGIS — used when custom MVT logic is needed.

Martin handles most MVT generation natively. This module is for cases where
you need filtered or aggregated tiles that Martin's config can't express.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MVTQuery:
    schema: str
    table: str
    z: int
    x: int
    y: int
    columns: list[str] | None = None    # None means all non-geom columns
    where: str | None = None             # Extra WHERE clause (e.g. "category = 'health'")
    extent: int = 4096
    buffer: int = 64


def build_mvt_sql(q: MVTQuery) -> tuple[str, list]:
    """
    Return (sql, params) for an ST_AsMVT query.

    Uses ST_TileEnvelope to compute the tile bounding box, then
    clips and simplifies geometry via ST_AsMVTGeom.
    """
    col_list = ", ".join(q.columns) if q.columns else ""
    col_select = f"id, {col_list}," if col_list else "id,"

    extra_where = f"AND ({q.where})" if q.where else ""

    sql = f"""
        SELECT ST_AsMVT(tile_data, '{q.table}', {q.extent}, 'mvt_geom') AS mvt
        FROM (
            SELECT
                {col_select}
                ST_AsMVTGeom(
                    ST_Transform(geom, 3857),
                    ST_TileEnvelope($1, $2, $3),
                    {q.extent},
                    {q.buffer},
                    true
                ) AS mvt_geom
            FROM {q.schema}.{q.table}
            WHERE geom && ST_Transform(ST_TileEnvelope($1, $2, $3), 4326)
              {extra_where}
        ) tile_data
        WHERE mvt_geom IS NOT NULL
    """.strip()

    return sql, [q.z, q.x, q.y]
