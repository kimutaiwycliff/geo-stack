-- 04_functions.sql
-- Reusable PL/pgSQL spatial helpers and triggers.

-- -------------------------------------------------------------------------
-- set_updated_at(): trigger function to auto-update the updated_at column.
-- Attach to any table with: CREATE TRIGGER ... BEFORE UPDATE ON geo.tablename
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach updated_at trigger to all geo tables
CREATE TRIGGER parcels_updated_at
    BEFORE UPDATE ON geo.parcels
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER boundaries_updated_at
    BEFORE UPDATE ON geo.boundaries
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER poi_updated_at
    BEFORE UPDATE ON geo.points_of_interest
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER raster_catalog_updated_at
    BEFORE UPDATE ON geo.raster_catalog
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- -------------------------------------------------------------------------
-- audit_geo_change(): append a row to audit.changes on any DML.
-- Captures full old/new row as JSONB for complete change history.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION audit.log_change()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit.changes (table_name, operation, row_id, old_data, new_data)
    VALUES (
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
        SUBSTR(TG_OP, 1, 1),
        CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END,
        CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
        CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END
    );
    RETURN NULL;  -- AFTER trigger, return value is ignored
END;
$$ LANGUAGE plpgsql;

-- Attach audit trigger to parcels (the most write-sensitive table)
CREATE TRIGGER parcels_audit
    AFTER INSERT OR UPDATE OR DELETE ON geo.parcels
    FOR EACH ROW EXECUTE FUNCTION audit.log_change();

-- -------------------------------------------------------------------------
-- geo.features_in_bbox(schema, table, xmin, ymin, xmax, ymax, lim)
-- Returns rows from any geo table intersecting a bounding box.
-- Used by the FastAPI /features endpoint to build dynamic queries.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION geo.features_in_bbox(
    p_schema  TEXT,
    p_table   TEXT,
    p_xmin    DOUBLE PRECISION,
    p_ymin    DOUBLE PRECISION,
    p_xmax    DOUBLE PRECISION,
    p_ymax    DOUBLE PRECISION,
    p_limit   INT DEFAULT 500
)
RETURNS TABLE (id BIGINT, geom GEOMETRY, properties JSONB) AS $$
DECLARE
    bbox GEOMETRY;
    sql  TEXT;
BEGIN
    bbox := ST_MakeEnvelope(p_xmin, p_ymin, p_xmax, p_ymax, 4326);
    sql := format(
        'SELECT id, geom, to_jsonb(t) - ''id'' - ''geom'' AS properties
         FROM %I.%I t
         WHERE geom && $1
         LIMIT %L',
        p_schema, p_table, p_limit
    );
    RETURN QUERY EXECUTE sql USING bbox;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- -------------------------------------------------------------------------
-- geo.nearest_features(schema, table, lon, lat, radius_m, lim)
-- KNN search: features within radius_m metres of a point, ordered by distance.
-- Uses PostGIS <-> operator with geography cast for metre-accurate distance.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION geo.nearest_features(
    p_schema   TEXT,
    p_table    TEXT,
    p_lon      DOUBLE PRECISION,
    p_lat      DOUBLE PRECISION,
    p_radius_m DOUBLE PRECISION DEFAULT 1000,
    p_limit    INT DEFAULT 10
)
RETURNS TABLE (id BIGINT, distance_m DOUBLE PRECISION, geom GEOMETRY, properties JSONB) AS $$
DECLARE
    origin GEOMETRY;
    sql    TEXT;
BEGIN
    origin := ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326);
    sql := format(
        'SELECT id,
                ST_Distance(geom::geography, $1::geography) AS distance_m,
                geom,
                to_jsonb(t) - ''id'' - ''geom'' AS properties
         FROM %I.%I t
         WHERE ST_DWithin(geom::geography, $1::geography, $2)
         ORDER BY geom::geography <-> $1::geography
         LIMIT %L',
        p_schema, p_table, p_limit
    );
    RETURN QUERY EXECUTE sql USING origin, p_radius_m;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- -------------------------------------------------------------------------
-- geo.mvt_query(schema, table, z, x, y)
-- Builds and executes an ST_AsMVT query for a single tile coordinate.
-- Martin handles this natively, but this function is useful for custom tile logic.
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION geo.mvt_tile(
    p_schema TEXT,
    p_table  TEXT,
    p_z      INT,
    p_x      INT,
    p_y      INT
)
RETURNS BYTEA AS $$
DECLARE
    tile_bbox GEOMETRY;
    sql       TEXT;
    result    BYTEA;
BEGIN
    tile_bbox := ST_TileEnvelope(p_z, p_x, p_y);
    sql := format(
        'SELECT ST_AsMVT(tile, %L, 4096, ''geom'')
         FROM (
             SELECT id,
                    ST_AsMVTGeom(
                        ST_Transform(geom, 3857),
                        ST_Transform($1, 3857),
                        4096, 64, true
                    ) AS geom,
                    to_jsonb(t) - ''geom'' AS properties
             FROM %I.%I t
             WHERE geom && ST_Transform($1, 4326)
         ) tile',
        p_table, p_schema, p_table
    );
    EXECUTE sql INTO result USING tile_bbox;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
