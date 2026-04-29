-- 02_tables.sql
-- Core spatial tables for geo-stack.
-- All geometry columns are EPSG:4326 (WGS84) — reproject inside queries when needed.
-- updated_at is maintained automatically by the trigger defined in 04_functions.sql.

-- -------------------------------------------------------------------------
-- geo.parcels: land parcel registry (write-heavy, KNN queries, LBIS use case)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo.parcels (
    id               BIGSERIAL PRIMARY KEY,
    parcel_number    VARCHAR(64) UNIQUE NOT NULL,
    owner_name       VARCHAR(255),
    area_ha          NUMERIC(12, 4),
    land_use         VARCHAR(64),
    tenure_type      VARCHAR(32),
    registration_date DATE,
    geom             GEOMETRY(MultiPolygon, 4326) NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT parcels_geom_valid CHECK (ST_IsValid(geom))
);

-- -------------------------------------------------------------------------
-- geo.boundaries: administrative boundaries (country → ward level)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo.boundaries (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    level      SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 5),
                         -- 0=country, 1=county/state, 2=sub-county, 3=ward, 4=village, 5=sub-village
    code       VARCHAR(32),
    country    VARCHAR(3) NOT NULL DEFAULT 'KEN',   -- ISO 3166-1 alpha-3
    parent_id  BIGINT REFERENCES geo.boundaries(id),
    geom       GEOMETRY(MultiPolygon, 4326) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT boundaries_geom_valid CHECK (ST_IsValid(geom))
);

-- -------------------------------------------------------------------------
-- geo.points_of_interest: named locations (schools, clinics, markets, etc.)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo.points_of_interest (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    category   VARCHAR(64) NOT NULL,   -- e.g. health, education, water, market
    subcategory VARCHAR(64),
    source     VARCHAR(64),            -- overture, osm, survey
    geom       GEOMETRY(Point, 4326) NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT poi_geom_valid CHECK (ST_IsValid(geom))
);

-- -------------------------------------------------------------------------
-- geo.raster_catalog: metadata for COG raster files (served by TiTiler)
-- Actual raster data lives in R2/S3; this table is just the catalog.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo.raster_catalog (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    description   TEXT,
    cog_url       TEXT NOT NULL,           -- Full HTTPS URL to the COG file
    bbox          GEOMETRY(Polygon, 4326), -- Extent of the raster
    resolution_m  NUMERIC(10, 2),
    band_count    SMALLINT,
    data_type     VARCHAR(32),             -- float32, uint8, etc.
    colormap      VARCHAR(64),             -- colormap name for TiTiler rendering
    acquired_at   DATE,
    created_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at    TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT raster_bbox_valid CHECK (bbox IS NULL OR ST_IsValid(bbox))
);

-- -------------------------------------------------------------------------
-- staging.raw_features: temporary landing zone for ogr2ogr imports
-- Cleaned and promoted to geo.* tables after validation.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.raw_features (
    id         BIGSERIAL PRIMARY KEY,
    source     VARCHAR(255),
    layer_name VARCHAR(255),
    properties JSONB,
    geom       GEOMETRY(Geometry, 4326),
    imported_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- -------------------------------------------------------------------------
-- audit.changes: tracks all INSERT/UPDATE/DELETE on geo tables
-- Populated by the trigger defined in 04_functions.sql.
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit.changes (
    id          BIGSERIAL PRIMARY KEY,
    table_name  VARCHAR(128) NOT NULL,
    operation   CHAR(1) NOT NULL CHECK (operation IN ('I', 'U', 'D')),
    row_id      BIGINT,
    old_data    JSONB,
    new_data    JSONB,
    changed_by  VARCHAR(128) DEFAULT current_user,
    changed_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
