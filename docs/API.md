# API reference

Base URL in development: `http://localhost:8000`
Interactive docs: `/docs` · OpenAPI schema: `/openapi.json`

All request and response bodies are JSON. Dates are `YYYY-MM-DD`. Coordinates
are GeoJSON `[longitude, latitude]` in EPSG:4326.

---

## Error envelope

Every non-2xx response has the same shape:

```json
{
  "code": "no_imagery",
  "message": "No Sentinel-2 scenes matched the AOI, date range and cloud filter.",
  "details": { }
}
```

| Code | HTTP | Meaning | What to do |
| --- | --- | --- | --- |
| `validation_error` | 422 | Request body failed schema validation | `details.errors[]` lists field, message, type |
| `invalid_aoi` | 422 | Geometry unusable — self-intersecting, too large, wrong CRS | Fix or redraw the AOI |
| `invalid_request` | 422 | Well-formed but semantically invalid | Read `message` |
| `no_imagery` | 404 | No scenes matched. **Expected, not a bug** | Widen the date range, raise `cloud_threshold` |
| `earth_engine_error` | 502 | Earth Engine rejected or failed the computation | Retry; if persistent, reduce AOI or scale |
| `earth_engine_auth_error` | 503 | Credentials missing, invalid, or lacking permission | Follow `details.remediation[]`; see [SETUP.md](SETUP.md) |
| `configuration_error` | 500 | Required server configuration missing | Check `.env` |
| `internal_error` | 500 | Unexpected failure | Check server logs; no stack trace is returned to clients |

`earth_engine_auth_error` always carries `details.remediation`, an array of
concrete setup steps. A misconfigured deployment explains itself.

## Local analysis history

Successful snapshot, time-series, and period-comparison requests are written to
the configured SQLite database (`DATABASE_PATH`). The local dashboard reads
recent entries from `GET /api/history?limit=20`, can read one entry from
`GET /api/history/{id}`, and removes an entry with
`DELETE /api/history/{id}`. Detail responses retain request geometry and
numeric analysis output, but omit signed map tile URLs because those expire.
This storage is single-user local history; it does not provide account-level
privacy or access control.

---

## `GET /`

Service index: name, version, and the paths below.

---

## `GET /health`

Liveness plus Earth Engine readiness.

**Returns HTTP 200 even when Earth Engine is unavailable** — check the body, not
the status code. This is intentional: an instance waiting on credentials should
not be silently removed from a load balancer without anyone seeing why.

```json
{
  "status": "degraded",
  "app_name": "CropSense API",
  "version": "0.1.0",
  "environment": "development",
  "earth_engine": {
    "initialized": false,
    "reachable": null,
    "auth_method": null,
    "project": null,
    "service_account_email": null,
    "high_volume_endpoint": true,
    "error": "No Earth Engine credentials found. Run `earthengine authenticate` …",
    "remediation": [
      "Set EE_PROJECT in your .env to a Google Cloud project ID that is registered for Earth Engine…",
      "Local development: install the Earth Engine CLI and run `earthengine authenticate`…"
    ]
  },
  "timestamp": "2026-08-26T09:14:02.118Z"
}
```

`status` is `"ok"` when Earth Engine initialised, `"degraded"` otherwise.
`reachable` is `null` until a live round trip has been performed — it
distinguishes "the library loaded" from "we can actually run analyses". Use
`/api/system/gee-test` for the latter.

---

## `GET /api/system/config`

Non-sensitive server defaults, so the frontend can mirror them without
hard-coding. Useful for pre-filling controls and rendering legends before any
analysis has run.

```json
{
  "collection_id": "COPERNICUS/S2_SR_HARMONIZED",
  "band_red": "B4",
  "band_nir": "B8",
  "default_cloud_mask_method": "cs_plus",
  "default_composite_method": "median",
  "default_scale_m": 10,
  "default_ndvi_class_thresholds": [0.2, 0.4, 0.6, 0.8],
  "default_decline_threshold": 0.15,
  "health_classes": [{ "key": "healthy", "label": "Healthy", "color": "#66bd63", "…": "…" }],
  "ndvi_palette": ["#a50026", "…", "#006837"],
  "max_aoi_area_km2": 2500.0,
  "max_date_range_days": 730,
  "calibration_note": "…generic starting points… calibrate for crop type and growth stage…",
  "limitations": ["…"]
}
```

This endpoint deliberately **does not** expose `EE_PROJECT`, the service-account
email, or anything credential-bearing. A test in
`backend/tests/test_api.py` asserts the response body contains none of
`private_key`, `service_account`, `ee_project` or `credential`.

---

## `GET /api/system/gee-test`

Performs two **real** Earth Engine round trips: a trivial arithmetic evaluation
(proves authentication and network egress), then a tightly bounded Sentinel-2
catalogue query (proves data access).

`200` on success, `503` with remediation when Earth Engine is unusable.

```json
{
  "success": true,
  "auth_method": "local_credentials",
  "project": "your-project-id",
  "round_trip_ms": 812,
  "server_side_number": 42.0,
  "sample_collection_id": "COPERNICUS/S2_SR_HARMONIZED",
  "sample_scene_count": 3,
  "sample_scene_id": "20240115T052121_20240115T052950_T43RFP",
  "message": "Earth Engine is reachable and the Sentinel-2 collection is queryable.",
  "remediation": []
}
```

---

## `POST /api/ndvi/analyze`

The main endpoint. Computes NDVI over an AOI for a date window, and returns
statistics, health classification and renderable map layers.

### Request

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `aoi` | GeoJSON | required | Geometry, Feature, or single-feature FeatureCollection, EPSG:4326 |
| `start_date` | date | required | Inclusive |
| `end_date` | date | required | Inclusive; must be ≥ `start_date` |
| `cloud_threshold` | 0–100 | `30` | Scene-level max `CLOUDY_PIXEL_PERCENTAGE` |
| `buffer_m` | 0–20000 | `250` | Applied to Point AOIs to form a circle |
| `options` | object | `{}` | See below |

`options` (all optional; `extra` fields are rejected):

| Field | Type | Notes |
| --- | --- | --- |
| `cloud_mask_method` | `cs_plus` \| `scl` \| `qa60` \| `none` | Default `cs_plus` |
| `composite_method` | `median` \| `mean` \| `greenest` \| `most_recent` | Default `median` |
| `scale_m` | 10–1000 | Default 10 (Sentinel-2 native for B4/B8) |
| `ndvi_class_thresholds` | `[float × 4]` | Strictly ascending, each in [−1, 1] |
| `cloud_score_plus_threshold` | 0.0–1.0 | Clearness cutoff; default 0.60 |
| `include_true_color_layer` | bool | Default `true` |

```json
{
  "aoi": {
    "type": "Polygon",
    "coordinates": [[[75.800,30.900],[75.812,30.900],[75.812,30.908],[75.800,30.908],[75.800,30.900]]]
  },
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "cloud_threshold": 30,
  "options": { "cloud_mask_method": "cs_plus", "composite_method": "median" }
}
```

### Response

| Field | Contents |
| --- | --- |
| `aoi` | Resolved `geometry_type`, `area_ha`, `area_km2`, `centroid` `[lon, lat]`, `bbox` `[min_lon, min_lat, max_lon, max_lat]` |
| `imagery` | Provenance: `scene_count`, `scene_dates`, `scene_ids`, mean scene cloud %, the mask and composite methods actually used |
| `statistics` | `mean`, `min`, `max`, `median`, `std_dev`, `p10`, `p90`, `valid_pixel_count`, `total_pixel_count`, `valid_pixel_fraction`, `scale_m` |
| `health` | `thresholds`, `thresholds_source`, `classes[]`, `dominant_class`, `classified_area_ha`, `calibration_note` |
| `layers` | Renderable `MapLayer` objects (see below) |
| `warnings` | Reliability caveats — **read these** |
| `notes` | Interpretation and limitation text for display in the UI |
| `computed_at`, `duration_ms` | Server timestamp and processing time |

Each entry in `health.classes` carries `key`, `label`, `color`, `ndvi_min`,
`ndvi_max`, `area_ha`, `percent_of_valid` and `pixel_count` — everything needed
for a stacked bar or donut chart with correct colours and bounds.

`statistics.valid_pixel_fraction` is the number to check before trusting
anything else. A mean built from 3% of a field is not a field mean, and the API
emits a warning when coverage is low.

### Map layers

```json
{
  "id": "ndvi",
  "name": "NDVI",
  "description": "Normalised Difference Vegetation Index from Sentinel-2 B8 (NIR) and B4 (Red) at 10 m…",
  "tile_url_template": "https://earthengine.googleapis.com/v1/projects/…/tiles/{z}/{x}/{y}",
  "attribution": "Contains modified Copernicus Sentinel data, processed via Google Earth Engine.",
  "opacity": 1.0,
  "legend": [{ "label": "0.40 - 0.60", "color": "#a6d96a", "value_min": 0.4, "value_max": 0.6 }],
  "value_range": [-0.2, 0.9]
}
```

`tile_url_template` is an XYZ template with `{x}`, `{y}`, `{z}` placeholders,
ready to hand to Leaflet's `L.tileLayer`. It is produced by
`ee.Image.getMapId()`: **signed, short-lived, and carrying no credential**, which
is what makes it safe to send to a browser. Treat it as valid for the current
session and re-request analysis when tiles stop loading.

Layer ids returned by `/analyze`: `ndvi`, `health`, and `true_color` when
`include_true_color_layer` is true.

---

## `POST /api/ndvi/timeseries`

Mean NDVI over time plus a linear trend.

Same AOI and option fields as `/analyze`, plus:

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `aggregation` | `scene` \| `weekly` \| `biweekly` \| `monthly` | `scene` | `scene` gives one point per usable overpass; calendar bins composite within each bin, filling cloud gaps at the cost of temporal precision |
| `min_valid_fraction` | 0.0–1.0 | `0.10` | Drop points whose cloud-free AOI coverage is below this. Prevents a 2%-visible scene from creating a fake dip |

Response adds:

* `points[]` — each with `date`, `mean_ndvi`, `min_ndvi`, `max_ndvi`,
  `median_ndvi`, `std_dev_ndvi`, `valid_pixel_fraction`, `scene_count`,
  `scene_cloud_percent`, `scene_id`. Plot `mean_ndvi` against `date`; use
  `valid_pixel_fraction` to style low-confidence points.
* `excluded_point_count` — observations dropped for falling below
  `min_valid_fraction`. Surface this so users know data was withheld.
* `trend` — `n_points`, `slope_ndvi_per_day`, `slope_ndvi_per_30_days`,
  `intercept`, `r_squared`, `direction`, `first_value`, `last_value`,
  `absolute_change`, `interpretation`.

The trend is ordinary least squares on the retained points, computed on the
server so it is reproducible. Vegetation through a season is not linear — over a
full phenological cycle the slope means very little. Show `r_squared` and
`n_points` alongside it, and prefer the chart to the number.

---

## `POST /api/ndvi/change`

Compares a baseline window against a recent window over the same AOI, and screens
for significant decline.

Same AOI and option fields as `/analyze`, plus:

| Field | Type | Notes |
| --- | --- | --- |
| `baseline_start_date`, `baseline_end_date` | date | The earlier reference period |
| `recent_start_date`, `recent_end_date` | date | Must start on or after the baseline start |
| `decline_threshold` | 0 < x ≤ 2 | Minimum NDVI drop that flags a pixel. Default 0.15 |

Response contains `baseline_imagery` / `recent_imagery`, `baseline_statistics` /
`recent_statistics`, `baseline_health` / `recent_health`, and:

```json
"change": {
  "mean_change": -0.08,
  "min_change": -0.42,
  "max_change": 0.11,
  "median_change": -0.07,
  "std_dev_change": 0.09,
  "comparable_area_ha": 8.6,
  "comparable_area_fraction": 0.86,
  "declined_area_ha": 1.9,
  "declined_percent_of_comparable": 22.1,
  "improved_area_ha": 0.3,
  "improved_percent_of_comparable": 3.5,
  "decline_threshold": 0.15
}
```

Layer ids: `ndvi_baseline`, `ndvi_recent`, `ndvi_change` (diverging palette) and
`potential_stress` (the decline mask). The first two let the UI show the two
periods side by side with an identical stretch.

Two things to render honestly:

1. **Only pixels cloud-free in both windows are compared.** The percentages are
   shares of `comparable_area_ha`, not of the field. Show
   `comparable_area_fraction` next to them.
2. **A flag is not a diagnosis.** Declining NDVI is equally consistent with
   harvest, tillage, lodging, waterlogging, drought, nutrient deficiency, pests,
   disease and normal senescence. The layer description and the `notes` array say
   so — display them. See [LIMITATIONS.md](LIMITATIONS.md).

---

## Notes for frontend implementers

* **Always render `warnings` and `notes`.** They are the difference between a
  number and an honest number. `warnings` covers low cloud-free coverage,
  single-scene composites and cloud-mask downgrades; `notes` carries the
  interpretation caveats.
* **Branch on `code`, not on HTTP status.** `404 no_imagery` deserves "no
  cloud-free imagery in this window — try widening the date range", not a generic
  error. `503 earth_engine_auth_error` deserves the `details.remediation` list
  rendered as a checklist.
* **Do not cache `tile_url_template`.** It expires.
* **Fetch `/api/system/config` once at startup** to populate defaults, the palette
  and the legend, rather than duplicating them in the client.
* **Show `health.thresholds` wherever classes are displayed**, along with
  `calibration_note`. A class label without its bounds invites over-reading.
