-- 05_sample_data.sql
-- Sample spatial data for Kenya / Nairobi to verify the stack is working.
-- This uses manually-crafted representative geometries based on real coordinates.
-- For production data, use scripts/overture_extract.py or scripts/load_postgis.sh.

-- -------------------------------------------------------------------------
-- Kenya administrative boundaries (simplified, level 0 and level 1)
-- Real ADM1 boundaries — source: GADM / Overture Maps approximations
-- -------------------------------------------------------------------------
INSERT INTO geo.boundaries (name, level, code, country, geom) VALUES
(
    'Kenya',
    0,
    'KEN',
    'KEN',
    ST_Multi(ST_GeomFromText(
        'POLYGON((33.9098987 -4.6755, 41.8995 -4.6755, 41.8995 5.0209, 33.9098987 5.0209, 33.9098987 -4.6755))',
        4326
    ))
)
ON CONFLICT DO NOTHING;

-- Nairobi County (simplified bounding polygon — real centroid: 36.8219°E, 1.2921°S)
INSERT INTO geo.boundaries (name, level, code, country, geom) VALUES
(
    'Nairobi',
    1,
    'KE-110',
    'KEN',
    ST_Multi(ST_GeomFromText(
        'POLYGON((36.6500 -1.4440, 37.1050 -1.4440, 37.1050 -1.1580, 36.6500 -1.1580, 36.6500 -1.4440))',
        4326
    ))
)
ON CONFLICT DO NOTHING;

-- Mombasa County
INSERT INTO geo.boundaries (name, level, code, country, geom) VALUES
(
    'Mombasa',
    1,
    'KE-111',
    'KEN',
    ST_Multi(ST_GeomFromText(
        'POLYGON((39.5700 -4.1800, 39.7500 -4.1800, 39.7500 -3.9800, 39.5700 -3.9800, 39.5700 -4.1800))',
        4326
    ))
)
ON CONFLICT DO NOTHING;

-- Kisumu County
INSERT INTO geo.boundaries (name, level, code, country, geom) VALUES
(
    'Kisumu',
    1,
    'KE-042',
    'KEN',
    ST_Multi(ST_GeomFromText(
        'POLYGON((34.5500 -0.2200, 35.0000 -0.2200, 35.0000 0.1800, 34.5500 0.1800, 34.5500 -0.2200))',
        4326
    ))
)
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------------------
-- Nairobi wards (simplified — 17 central wards with approximate boundaries)
-- Real ward boundaries are in data/sample/nairobi_wards.parquet
-- -------------------------------------------------------------------------
INSERT INTO geo.boundaries (name, level, code, country, parent_id, geom)
SELECT
    ward_name,
    3,
    ward_code,
    'KEN',
    (SELECT id FROM geo.boundaries WHERE code = 'KE-110' LIMIT 1),
    ST_Multi(ST_GeomFromText(ward_geom, 4326))
FROM (VALUES
    ('Westlands',      'KE-110-001', 'POLYGON((36.7900 -1.2800, 36.8350 -1.2800, 36.8350 -1.2450, 36.7900 -1.2450, 36.7900 -1.2800))'),
    ('Parklands',      'KE-110-002', 'POLYGON((36.8100 -1.2750, 36.8450 -1.2750, 36.8450 -1.2500, 36.8100 -1.2500, 36.8100 -1.2750))'),
    ('Starehe',        'KE-110-003', 'POLYGON((36.8200 -1.2950, 36.8550 -1.2950, 36.8550 -1.2700, 36.8200 -1.2700, 36.8200 -1.2950))'),
    ('Langata',        'KE-110-004', 'POLYGON((36.7200 -1.3650, 36.8000 -1.3650, 36.8000 -1.3100, 36.7200 -1.3100, 36.7200 -1.3650))'),
    ('Kibra',          'KE-110-005', 'POLYGON((36.7600 -1.3200, 36.8000 -1.3200, 36.8000 -1.2950, 36.7600 -1.2950, 36.7600 -1.3200))'),
    ('Makadara',       'KE-110-006', 'POLYGON((36.8450 -1.3100, 36.8850 -1.3100, 36.8850 -1.2850, 36.8450 -1.2850, 36.8450 -1.3100))'),
    ('Embakasi East',  'KE-110-007', 'POLYGON((36.8850 -1.3400, 36.9450 -1.3400, 36.9450 -1.2950, 36.8850 -1.2950, 36.8850 -1.3400))'),
    ('Embakasi West',  'KE-110-008', 'POLYGON((36.8250 -1.3400, 36.8850 -1.3400, 36.8850 -1.2950, 36.8250 -1.2950, 36.8250 -1.3400))'),
    ('Kasarani',       'KE-110-009', 'POLYGON((36.8600 -1.2700, 36.9200 -1.2700, 36.9200 -1.2100, 36.8600 -1.2100, 36.8600 -1.2700))'),
    ('Roysambu',       'KE-110-010', 'POLYGON((36.8300 -1.2350, 36.9000 -1.2350, 36.9000 -1.1900, 36.8300 -1.1900, 36.8300 -1.2350))'),
    ('Ruaraka',        'KE-110-011', 'POLYGON((36.8700 -1.2700, 36.9100 -1.2700, 36.9100 -1.2400, 36.8700 -1.2400, 36.8700 -1.2700))'),
    ('Dagoretti North','KE-110-012', 'POLYGON((36.7300 -1.3050, 36.7800 -1.3050, 36.7800 -1.2700, 36.7300 -1.2700, 36.7300 -1.3050))'),
    ('Dagoretti South','KE-110-013', 'POLYGON((36.7200 -1.3400, 36.7800 -1.3400, 36.7800 -1.3050, 36.7200 -1.3050, 36.7200 -1.3400))'),
    ('Mathare',        'KE-110-014', 'POLYGON((36.8450 -1.2700, 36.8850 -1.2700, 36.8850 -1.2450, 36.8450 -1.2450, 36.8450 -1.2700))'),
    ('Pumwani',        'KE-110-015', 'POLYGON((36.8300 -1.2950, 36.8600 -1.2950, 36.8600 -1.2700, 36.8300 -1.2700, 36.8300 -1.2950))'),
    ('Kamukunji',      'KE-110-016', 'POLYGON((36.8500 -1.2850, 36.8800 -1.2850, 36.8800 -1.2600, 36.8500 -1.2600, 36.8500 -1.2850))'),
    ('Njiru',          'KE-110-017', 'POLYGON((36.9200 -1.3000, 37.0000 -1.3000, 37.0000 -1.2300, 36.9200 -1.2300, 36.9200 -1.3000))')
) AS w(ward_name, ward_code, ward_geom)
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------------------
-- Sample points of interest in Nairobi
-- -------------------------------------------------------------------------
INSERT INTO geo.points_of_interest (name, category, subcategory, source, geom, properties) VALUES
('Kenyatta National Hospital',    'health',     'hospital',       'osm', ST_SetSRID(ST_MakePoint(36.8056, -1.3014), 4326), '{"beds": 1800, "level": "national_referral"}'::jsonb),
('University of Nairobi',         'education',  'university',     'osm', ST_SetSRID(ST_MakePoint(36.8165, -1.2797), 4326), '{"founded": 1956, "students": 85000}'::jsonb),
('JKIA Jomo Kenyatta Airport',    'transport',  'airport',        'osm', ST_SetSRID(ST_MakePoint(36.9275, -1.3192), 4326), '{"iata": "NBO", "runways": 2}'::jsonb),
('Westgate Shopping Mall',        'commercial', 'shopping_mall',  'osm', ST_SetSRID(ST_MakePoint(36.8027, -1.2575), 4326), '{"floors": 4}'::jsonb),
('Uhuru Park',                    'leisure',    'park',           'osm', ST_SetSRID(ST_MakePoint(36.8167, -1.2889), 4326), '{"area_ha": 12.2}'::jsonb),
('Nairobi National Museum',       'tourism',    'museum',         'osm', ST_SetSRID(ST_MakePoint(36.8119, -1.2724), 4326), '{"founded": 1910}'::jsonb),
('City Market Nairobi',           'commercial', 'market',         'osm', ST_SetSRID(ST_MakePoint(36.8188, -1.2839), 4326), '{"type": "indoor"}'::jsonb),
('Nairobi Hospital',              'health',     'hospital',       'osm', ST_SetSRID(ST_MakePoint(36.7989, -1.2958), 4326), '{"type": "private"}'::jsonb),
('Kibera Health Centre',          'health',     'health_centre',  'survey', ST_SetSRID(ST_MakePoint(36.7836, -1.3129), 4326), '{"level": "2"}'::jsonb),
('Aga Khan University Hospital',  'health',     'hospital',       'osm', ST_SetSRID(ST_MakePoint(36.8123, -1.2596), 4326), '{"type": "private"}'::jsonb),
('Two Rivers Mall',               'commercial', 'shopping_mall',  'osm', ST_SetSRID(ST_MakePoint(36.7983, -1.2025), 4326), '{"gla_m2": 67000}'::jsonb),
('Nairobi Railway Station',       'transport',  'train_station',  'osm', ST_SetSRID(ST_MakePoint(36.8344, -1.2961), 4326), '{"lines": ["commuter_rail", "sgr"]}'::jsonb)
ON CONFLICT DO NOTHING;

-- -------------------------------------------------------------------------
-- Sample parcels (fictional, for schema validation only)
-- -------------------------------------------------------------------------
INSERT INTO geo.parcels (parcel_number, owner_name, area_ha, land_use, tenure_type, geom) VALUES
('NRB/WEST/001/2024', 'Wanjiku Holdings Ltd',    0.4523, 'residential',  'freehold', ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(36.8050, -1.2800), 4326)::geography, 50)::geometry)),
('NRB/STAR/002/2024', 'Oduya Family Trust',      1.2100, 'commercial',   'leasehold', ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(36.8300, -1.2850), 4326)::geography, 80)::geometry)),
('NRB/KASA/003/2024', 'Gitau & Sons Properties', 0.8900, 'mixed_use',    'freehold', ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(36.8950, -1.2500), 4326)::geography, 65)::geometry))
ON CONFLICT DO NOTHING;

-- Verify sample data loaded correctly
DO $$
DECLARE
    n_boundaries INT;
    n_poi        INT;
    n_parcels    INT;
BEGIN
    SELECT COUNT(*) INTO n_boundaries FROM geo.boundaries;
    SELECT COUNT(*) INTO n_poi        FROM geo.points_of_interest;
    SELECT COUNT(*) INTO n_parcels    FROM geo.parcels;
    RAISE NOTICE 'Sample data loaded: % boundaries, % POIs, % parcels', n_boundaries, n_poi, n_parcels;
END
$$;
