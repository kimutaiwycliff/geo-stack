#!/usr/bin/env python3
"""
overture_extract.py — Extract Overture Maps data for a bbox → GeoParquet
=========================================================================
Usage:
  python scripts/overture_extract.py --bbox "36.65,-1.44,37.10,-1.16" --theme divisions
  python scripts/overture_extract.py --bbox "36.65,-1.44,37.10,-1.16" --theme places
  python scripts/overture_extract.py --bbox "33.9,-4.7,41.9,5.0" --theme divisions --output data/sample/kenya_admin.parquet

Available Overture themes:
  divisions  → Administrative boundaries (country, county, ward)
  places     → Points of interest
  buildings  → Building footprints
  transportation → Roads and paths
  base       → Land use, water, etc.

Requires: duckdb (with httpfs extension)
Install:  pip install duckdb

Data source: Overture Maps Foundation on AWS S3 (public, no auth required)
License: CDLA Permissive 2.0
"""

import argparse
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb not installed. Run: pip install duckdb")
    sys.exit(1)

# Overture Maps S3 paths (public bucket, no credentials needed)
OVERTURE_S3_BASE = "s3://overturemaps-us-west-2/release/2024-11-13.0"

THEME_PATHS = {
    "divisions":       f"{OVERTURE_S3_BASE}/theme=divisions/type=division_area/*.parquet",
    "places":          f"{OVERTURE_S3_BASE}/theme=places/type=place/*.parquet",
    "buildings":       f"{OVERTURE_S3_BASE}/theme=buildings/type=building/*.parquet",
    "transportation":  f"{OVERTURE_S3_BASE}/theme=transportation/type=segment/*.parquet",
    "base":            f"{OVERTURE_S3_BASE}/theme=base/type=land_use/*.parquet",
}

# Column selections per theme (Overture schemas vary by theme)
THEME_COLUMNS = {
    "divisions": "id, subtype AS level, names.primary AS name, country, geometry",
    "places":    "id, names.primary AS name, categories.primary AS category, geometry",
    "buildings": "id, height, num_floors, class, geometry",
    "transportation": "id, subtype, class, geometry",
    "base":      "id, subtype, class, geometry",
}


def extract(
    bbox: str,
    theme: str,
    output: str | None = None,
    limit: int | None = None,
) -> None:
    if theme not in THEME_PATHS:
        print(f"ERROR: Unknown theme '{theme}'. Available: {list(THEME_PATHS.keys())}")
        sys.exit(1)

    parts = [float(x) for x in bbox.split(",")]
    if len(parts) != 4:
        print("ERROR: bbox must be 'xmin,ymin,xmax,ymax'")
        sys.exit(1)
    xmin, ymin, xmax, ymax = parts

    if output is None:
        output = f"data/sample/overture_{theme}_{xmin:.1f}_{ymin:.1f}.parquet"

    Path(output).parent.mkdir(parents=True, exist_ok=True)

    s3_path = THEME_PATHS[theme]
    cols = THEME_COLUMNS[theme]
    limit_clause = f"LIMIT {limit}" if limit else ""

    print(f"[overture] Extracting {theme} for bbox [{xmin}, {ymin}, {xmax}, {ymax}]")
    print(f"[overture] Source: {s3_path}")

    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    # Overture is on AWS public S3 — anonymous access
    conn.execute("SET s3_region = 'us-west-2';")
    conn.execute("SET s3_url_style = 'vhost';")

    sql = f"""
        COPY (
            SELECT {cols}
            FROM read_parquet('{s3_path}', hive_partitioning=true)
            WHERE bbox.xmin <= {xmax}
              AND bbox.xmax >= {xmin}
              AND bbox.ymin <= {ymax}
              AND bbox.ymax >= {ymin}
            {limit_clause}
        )
        TO '{output}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """

    print(f"[overture] Running query...")
    conn.execute(sql)

    result = conn.execute(
        f"SELECT COUNT(*) FROM read_parquet('{output}')"
    ).fetchone()
    count = result[0] if result else 0
    size_mb = Path(output).stat().st_size / 1_048_576

    print(f"[overture] Done: {count:,} features → {output} ({size_mb:.1f} MB)")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bbox", required=True, help="xmin,ymin,xmax,ymax (EPSG:4326)")
    parser.add_argument("--theme", required=True, choices=list(THEME_PATHS.keys()))
    parser.add_argument("--output", help="Output path (default: data/sample/overture_{theme}.parquet)")
    parser.add_argument("--limit", type=int, help="Limit number of features (useful for testing)")

    args = parser.parse_args()
    extract(args.bbox, args.theme, args.output, args.limit)


if __name__ == "__main__":
    main()
