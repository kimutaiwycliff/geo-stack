/**
 * layers.ts — Project layer registry
 * ====================================
 * This is the MAIN FILE TO EDIT when starting a new project.
 * Add your layers here. The MapLibre component reads this config
 * and renders controls automatically.
 *
 * Layer types:
 *
 *   'mvt'      — Live vector tiles from Martin (PostGIS → browser)
 *                Use when: data changes daily, you need server-side auth,
 *                or the dataset is too large for GeoJSON.
 *                Source: Martin at PUBLIC_MARTIN_URL
 *
 *   'pmtiles'  — Pre-generated tiles from a .pmtiles file (serverless)
 *                Use when: data changes rarely (weekly/monthly),
 *                you want zero server cost, or need offline support.
 *                Generate with: scripts/to_pmtiles.sh
 *                Host on: Cloudflare R2 (free range-request support)
 *
 *   'geojson'  — Dynamic GeoJSON from FastAPI (supports filters)
 *                Use when: data needs aggregation/filtering,
 *                feature count is small (<5000 features in viewport),
 *                or you need DuckDB analytics on the result.
 *                Source: FastAPI at PUBLIC_API_URL/features/{layer}
 *
 *   'raster'   — Raster tiles from TiTiler (COG files)
 *                Use when: data is raster (imagery, DEM, climate grids,
 *                NDVI, rainfall, flood depth).
 *                Source: TiTiler at PUBLIC_TITILER_URL
 *
 * Tile source decision guide:
 *   ┌─────────────────────────────┬──────────────┐
 *   │ Data changes daily?         │ → use 'mvt'  │
 *   │ Data is static/archived?    │ → use 'pmtiles' │
 *   │ Needs filter/aggregate?     │ → use 'geojson' │
 *   │ Data is raster/imagery?     │ → use 'raster' │
 *   └─────────────────────────────┴──────────────┘
 */

export interface LayerConfig {
  /** Unique ID — used as MapLibre source and layer ID */
  id: string;

  /** Display label in the layer control panel */
  label: string;

  /** Layer type determines how tiles/data are loaded */
  type: 'mvt' | 'pmtiles' | 'geojson' | 'raster';

  /**
   * Tile URL template or file path:
   * - mvt:     '{PUBLIC_MARTIN_URL}/geo.parcels/{z}/{x}/{y}'
   * - pmtiles: 'https://r2-public.example.com/parcels.pmtiles'
   * - geojson: '{PUBLIC_API_URL}/features/parcels'
   * - raster:  '{PUBLIC_TITILER_URL}/cog/tiles/{z}/{x}/{y}.png?url=...'
   *
   * Use runtime config from /api/config (served by +server.ts) for dynamic URLs.
   * Never hardcode URLs here — they change between local/cloud/production.
   */
  url: string;

  /**
   * Vector layer name inside the tile (MVT and PMTiles only).
   * For Martin: use the full 'schema.table' form — Martin names the vector layer
   * 'geo.parcels', NOT 'parcels'. Check with:
   *   curl http://localhost:3000/geo.my_table | python3 -m json.tool | grep '"id"'
   */
  sourceLayer?: string;

  /** MapLibre GL paint specification — controls colours, widths, opacities */
  paint?: Record<string, unknown>;

  /** MapLibre GL layout specification — controls visibility, text labels */
  layout?: Record<string, unknown>;

  /** Minimum zoom level to show this layer */
  minzoom?: number;

  /** Maximum zoom level to show this layer */
  maxzoom?: number;

  /** Whether the layer is visible on initial load */
  visible?: boolean;

  /**
   * Feature property keys to show in the click popup.
   * First key is used as the popup title if it contains a name-like value.
   */
  popupFields?: string[];

  /**
   * Bounding box to zoom to when the user clicks the zoom button.
   * Format: [west, south, east, north] in EPSG:4326 (WGS84 decimal degrees).
   *
   * If omitted, zoom-to falls back to computing bounds from loaded source features.
   * Always set this for MVT and PMTiles layers — querying their source features
   * only returns tiles already in the viewport, so auto-detection is unreliable.
   *
   * For GeoJSON layers the API returns all features so auto-detection works fine,
   * but an explicit bounds is still faster (no source query needed).
   *
   * Example for Nairobi: bounds: [36.65, -1.44, 37.10, -1.16]
   */
  bounds?: [number, number, number, number];

  /**
   * Show a popup on hover in addition to the click popup.
   * The hover popup follows the cursor and disappears when the mouse leaves.
   * Toggle per-layer at runtime via the hover icon in the layer control.
   * Only works for layers with popupFields defined.
   */
  hoverPopup?: boolean;
}

/**
 * LAYER REGISTRY
 * ==============
 * Add your project layers here. This array drives the entire UI:
 * layer controls, click handlers, and legend are all generated from it.
 *
 * For a new Kenya flood risk project you might add:
 *   {
 *     id: 'flood-risk',
 *     label: 'Flood Risk Zones',
 *     type: 'pmtiles',   // pre-generated, no server needed
 *     url: 'https://pub-xxxx.r2.dev/kenya_flood_risk_2024.pmtiles',
 *     sourceLayer: 'flood_risk',
 *     paint: {
 *       'fill-color': ['match', ['get', 'risk_level'],
 *         'high',   '#ef4444',
 *         'medium', '#f97316',
 *         'low',    '#84cc16',
 *                   '#e5e7eb'
 *       ],
 *       'fill-opacity': 0.6,
 *     },
 *     popupFields: ['area_name', 'risk_level', 'affected_population'],
 *     visible: true,
 *   }
 */

// URLs are injected at runtime from /api/config — see +server.ts
// These defaults work for local development (docker-compose.local.yml)
const API_URL = typeof window !== 'undefined'
  ? (window as Window & { __GEO_CONFIG__?: { apiUrl: string } }).__GEO_CONFIG__?.apiUrl ?? 'http://localhost:8000'
  : 'http://localhost:8000';

const MARTIN_URL = typeof window !== 'undefined'
  ? (window as Window & { __GEO_CONFIG__?: { martinUrl: string } }).__GEO_CONFIG__?.martinUrl ?? 'http://localhost:3000'
  : 'http://localhost:3000';

export const layers: LayerConfig[] = [
  // ─── Administrative boundaries (MVT from Martin / PostGIS) ───────────────
  // Changes rarely but must be queryable at all zoom levels → MVT is ideal.
  {
    id: 'boundaries',
    label: 'Admin_0_Countries',
    type: 'mvt',
    url: `${MARTIN_URL}/geo.adm_adm_0/{z}/{x}/{y}`,
    sourceLayer: 'geo.adm_adm_0',
    paint: {
      'line-color': '#ae4713ff',
      'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1, 10, 2],
      'line-opacity': 0.8,
    },
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    minzoom: 2,
    maxzoom: 23,
    visible: true,
    popupFields: ['country', 'gid_0'],
    bounds: [33.9095880000001, -4.72041700099993, 41.9262161260002, 5.06116580999998],   // Kenya extent
  },

  // ─── Nairobi wards (PMTiles — static, zero-cost serving from R2) ──────────
  // Ward boundaries don't change → PMTiles is the right choice.
  // Generate: scripts/to_pmtiles.sh data/sample/nairobi_wards.parquet data/pmtiles/nairobi_wards.pmtiles
  // Upload:   scripts/r2_sync.sh data/pmtiles/
  {
    id: 'nairobi-wards',
    label: 'Nairobi Wards',
    type: 'pmtiles',
    url: '/data/pmtiles/nairobi_wards.pmtiles',   // Replace with R2 URL in production
    sourceLayer: 'nairobi_wards',
    paint: {
      'fill-color': '#3b82f6',
      'fill-opacity': 0.15,
      'fill-outline-color': '#1d4ed8',
    },
    minzoom: 10,
    maxzoom: 18,
    visible: false,   // Off by default — enable for Nairobi-specific projects
    popupFields: ['name', 'code'],
    bounds: [36.65, -1.44, 37.10, -1.16],   // Nairobi metro
  },

  // ─── Points of interest (GeoJSON from FastAPI) ────────────────────────────
  // Live query so you can filter by category, bbox, etc. via URL params.
  // Feature count stays small at city scale → GeoJSON is fine.
  {
    id: 'poi',
    label: 'Points of Interest',
    type: 'geojson',
    url: `${API_URL}/features/points_of_interest`,
    paint: {
      'circle-color': ['match', ['get', 'category'],
        'health',     '#ef4444',
        'education',  '#3b82f6',
        'transport',  '#8b5cf6',
        'commercial', '#f59e0b',
        'leisure',    '#10b981',
        'tourism',    '#ec4899',
                      '#6b7280',
      ],
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 4, 16, 8],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
      'circle-opacity': 0.9,
    },
    minzoom: 10,
    maxzoom: 22,
    visible: true,
    popupFields: ['name', 'category', 'subcategory'],
    bounds: [36.65, -1.44, 37.10, -1.16],   // Nairobi metro
    hoverPopup: true,
  },

  // ─── Land parcels (MVT from Martin) ──────────────────────────────────────
  // Write-heavy, KNN queries, audit trail → must live in PostGIS → MVT.
  {
    id: 'parcels',
    label: 'Land Parcels',
    type: 'mvt',
    url: `${MARTIN_URL}/geo.parcels/{z}/{x}/{y}`,
    sourceLayer: 'geo.parcels',
    paint: {
      'fill-color': '#d8120fff',
      'fill-opacity': 0.3,
      'fill-outline-color': '#d97706',
    },
    minzoom: 10,
    maxzoom: 22,
    visible: false,
    popupFields: ['parcel_number', 'owner_name', 'area_ha', 'land_use'],
    bounds: [36.78, -1.32, 36.87, -1.25],   // Nairobi central (parcel-scale)
  },
  {                                                                                                                                                              
    id: 'kenya-roads',                                                                                                                                           
    label: 'Kenya Roads (OSM)',                                                                                                                                  
    type: 'mvt',                                                                                                                                                 
    url: `${MARTIN_URL}/geo.kenya_roads/{z}/{x}/{y}`,
    sourceLayer: 'geo.kenya_roads',                                                                                                                              
    paint: {                                                                                                                                                   
      'line-color': ['match', ['get', 'fclass'],                                                                                                                 
        'motorway',  '#ef4444',                                                                                                                                  
        'trunk',     '#f97316',                                                                                                                                  
        'primary',   '#f59e0b',                                                                                                                                  
        'secondary', '#84cc16',                                                                                                                                  
        'tertiary',  '#6b7280',                                                                                                                                  
                     '#3e4137ff',
      ],                                                                                                                                                         
      'line-width': ['interpolate', ['linear'], ['zoom'],                                                                                                      
        6,  ['match', ['get', 'fclass'], 'motorway', 2, 'trunk', 1.5, 0.5],                                                                                      
        14, ['match', ['get', 'fclass'], 'motorway', 6, 'trunk', 4, 'primary', 3, 1.5],                                                                          
      ],                                                                                                                                                         
      'line-opacity': 0.85,                                                                                                                                      
    },                                                                                                                                                           
    minzoom: 5,                                                                                                                                                  
    maxzoom: 18,
    visible: true,                                                                                                                                               
    popupFields: ['name', 'fclass', 'ref', 'maxspeed', 'oneway'],                                                                                              
    bounds: [33.91, -4.73, 42.08, 5.28],                                                                                                                         
  },
];
