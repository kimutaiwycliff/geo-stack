-- 03_indexes.sql
-- Spatial (GiST) and attribute indexes for all geo tables.
-- GiST indexes are mandatory on every geometry column — without them spatial
-- queries degrade to full-table scans even with PostGIS.

-- geo.parcels
CREATE INDEX IF NOT EXISTS parcels_geom_gist   ON geo.parcels USING GIST (geom);
CREATE INDEX IF NOT EXISTS parcels_number_idx  ON geo.parcels (parcel_number);
CREATE INDEX IF NOT EXISTS parcels_land_use_idx ON geo.parcels (land_use);
CREATE INDEX IF NOT EXISTS parcels_updated_idx ON geo.parcels (updated_at DESC);

-- geo.boundaries
CREATE INDEX IF NOT EXISTS boundaries_geom_gist  ON geo.boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS boundaries_level_idx  ON geo.boundaries (level);
CREATE INDEX IF NOT EXISTS boundaries_country_idx ON geo.boundaries (country);
CREATE INDEX IF NOT EXISTS boundaries_parent_idx ON geo.boundaries (parent_id);
-- Text search on boundary names (trigram for partial match)
CREATE INDEX IF NOT EXISTS boundaries_name_trgm  ON geo.boundaries USING GIN (name gin_trgm_ops);

-- geo.points_of_interest
CREATE INDEX IF NOT EXISTS poi_geom_gist      ON geo.points_of_interest USING GIST (geom);
CREATE INDEX IF NOT EXISTS poi_category_idx   ON geo.points_of_interest (category);
CREATE INDEX IF NOT EXISTS poi_name_trgm      ON geo.points_of_interest USING GIN (name gin_trgm_ops);
-- JSONB properties index for arbitrary key lookups
CREATE INDEX IF NOT EXISTS poi_properties_gin ON geo.points_of_interest USING GIN (properties);

-- geo.raster_catalog
CREATE INDEX IF NOT EXISTS raster_bbox_gist   ON geo.raster_catalog USING GIST (bbox);
CREATE INDEX IF NOT EXISTS raster_name_idx    ON geo.raster_catalog (name);

-- staging.raw_features
CREATE INDEX IF NOT EXISTS raw_features_geom_gist ON staging.raw_features USING GIST (geom);
CREATE INDEX IF NOT EXISTS raw_features_source_idx ON staging.raw_features (source, layer_name);

-- audit.changes
CREATE INDEX IF NOT EXISTS audit_table_idx    ON audit.changes (table_name, changed_at DESC);
CREATE INDEX IF NOT EXISTS audit_row_idx      ON audit.changes (table_name, row_id);
