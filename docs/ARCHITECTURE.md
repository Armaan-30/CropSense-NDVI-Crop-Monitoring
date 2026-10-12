# Architecture

## Layering

```
┌───────────────────────────────────────────────────────────────┐
│  PRESENTATION                                    frontend/    │
│  React + TypeScript · Leaflet · charts                        │
│  Draws the AOI, renders tile layers, plots time series.        │
│  Holds no Google credentials.                                 │
└───────────────────────────┬───────────────────────────────────┘
                            │  JSON over HTTP
┌───────────────────────────▼───────────────────────────────────┐
│  API                                          app/api/        │
│  routes/{system,ndvi}.py    HTTP surface, logging             │
│  dependencies.py            DI providers — the only seam      │
│  router.py                  mounting and prefixes             │
│  ── validation by pydantic schemas, errors by one envelope ── │
└───────────────────────────┬───────────────────────────────────┘
                            │  typed request models
┌───────────────────────────▼───────────────────────────────────┐
│  ORCHESTRATION                    app/services/               │
│  analysis_service.py                                          │
│  Owns the pipeline: resolve options → build collection →      │
│  composite → compute → reduce → classify → assemble response. │
│  Decides what is a warning. Knows nothing about HTTP.         │
└──────────┬─────────────────────────────┬──────────────────────┘
           │                             │
┌──────────▼──────────────┐   ┌──────────▼──────────────────────┐
│  ANALYSIS               │   │  NUMERICS                       │
│  ndvi_service.py        │   │  metrics.py                     │
│  NDVI expressions,      │   │  Pure Python. NO `import ee`.   │
│  classification,        │   │  Percentages, ha conversion,    │
│  vis params, legends.   │   │  OLS trend, warning thresholds. │
│  Builds; never executes.│   │  Fully unit-testable offline.   │
└──────────┬──────────────┘   └─────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────┐
│  EARTH ENGINE GATEWAY                app/services/            │
│  gee_service.py  ── the ONLY module that imports and calls    │
│                     the Earth Engine client ──                │
│  Auth · collection building · cloud masking · compositing ·   │
│  reducers · getInfo · pixelArea · getMapId · error mapping    │
└──────────┬────────────────────────────────────────────────────┘
           │  earthengine-api
┌──────────▼────────────────────────────────────────────────────┐
│  GOOGLE EARTH ENGINE                                          │
│  COPERNICUS/S2_SR_HARMONIZED                                  │
│  GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED                     │
└───────────────────────────────────────────────────────────────┘
```

Cross-cutting, used by every layer: `app/core/config.py` (settings),
`app/core/exceptions.py` (domain errors), `app/core/logging_config.py`,
`app/models/vegetation.py` (health classes, palettes, science caveats),
`app/schemas/` (the API contract).

---

## The three boundaries that matter

### 1. Only `gee_service.py` touches Earth Engine

Authentication, catalogue queries, cloud masking, compositing, reducers, every
`getInfo()` call, area computation and tile registration are all inside one
module. Nothing above it imports `ee` for anything but type annotations.

*Why:* the spec asked for the Earth Engine integration to be isolated, and the
isolation pays off concretely. Changing the cloud-mask product, moving to
Landsat, switching from user credentials to a service account, or adding a
retry policy each touch one file. It is also the module most likely to break
when Google changes an API, so keeping the blast radius small is worth the
indirection.

### 2. `metrics.py` imports no `ee`

Every numeric decision — class percentages, pixel-count-to-hectare conversion,
the OLS trend fit, the rules that decide when coverage is too low to trust — is
plain Python operating on plain numbers.

*Why:* it makes the parts most likely to be *quietly* wrong testable without
credentials. The 115-test suite runs offline, and roughly a
third of it is arithmetic that would otherwise need a live Earth Engine session
to exercise. A rounding error in a hectare figure is a real bug that this
arrangement catches.

### 3. `app/api/dependencies.py` is the single DI seam

```python
def app_settings() -> Settings: ...
def earth_engine_service() -> GEEService: ...
def analysis_service(
    gee: GEEService = Depends(earth_engine_service),
    settings: Settings = Depends(app_settings),
) -> AnalysisService: ...
```

Routes depend on these providers, never on the service modules' own factories.

*Why:* FastAPI dependency overrides only reach dependencies that are actually
declared in the dependency graph. `AnalysisService` originally called
`get_gee_service()` internally, so overriding the Earth Engine client in tests
had no effect on the NDVI routes — they kept using the real singleton. Chaining
`analysis_service` off `earth_engine_service` means one override covers every
route beneath it.

Overrides still do **not** apply to the lifespan, which runs before request
handling and calls `get_gee_service()` directly. `tests/conftest.py` handles that
separately by replacing the module-level singleton in a session-scoped autouse
fixture.

---

## Request flow: `POST /api/ndvi/analyze`

```
 1  routes/ndvi.py       pydantic validates the body
                         AOI normalised (Feature/FeatureCollection → geometry),
                         dates ordered, thresholds ascending and in [-1,1]
                         ↓
 2  analysis_service     resolve options against settings
                         downgrade cs_plus → scl before 2017-06-27, warn
                         ↓
 3  gee_service          build_geometry()      GeoJSON → ee.Geometry
                         summarize_aoi()       area, centroid, bbox   [1 getInfo]
                         guard: AOI ≤ MAX_AOI_AREA_KM2
                         ↓
 4  gee_service          build_sentinel2_collection()
                         filterBounds → filterDate → CLOUDY_PIXEL_PERCENTAGE
                         per-pixel mask (Cloud Score+ join / SCL / QA60 / none)
                         scale DN → reflectance (×1e-4)
                         ↓
 5  gee_service          require_non_empty()   → 404 no_imagery if zero  [1 getInfo]
                         collection_metadata() scene ids, dates, cloud %  [1 getInfo]
                         ↓
 6  gee_service          composite()  median | mean | greenest | most_recent
                         ↓
 7  ndvi_service         add_ndvi_band()  (B8 − B4) / (B8 + B4)
                         ↓
 8  gee_service          reduce_statistics()   mean/min/max/median/sd/p10/p90  [1]
                         reduce_valid_area_m2() cloud-free area              [1]
                         ↓
 9  ndvi_service         classify_health()  cascade of where() over thresholds
10  gee_service          reduce_area_by_class()  pixelArea grouped by class  [1]
                         ↓
11  metrics.py           percentages, hectares, dominant class,
                         reliability warnings (low coverage, single scene)
                         ↓
12  ndvi_service         build_*_layer() → getMapId()  signed tile URLs     [3]
                         ↓
13  routes/ndvi.py       NDVIAnalyzeResponse
```

`[n]` marks a network round trip. Roughly eight to ten per analysis, which is why
the high-volume Earth Engine endpoint is the default — it is tuned for many small
interactive requests rather than a few large batch jobs.

Everything before step 8 is lazy: Earth Engine expressions are graphs, not
computations. Nothing executes until a `getInfo()` or `getMapId()` forces it.

---

## Configuration

`pydantic-settings` reads environment variables, resolving in this order:

1. Real process environment
2. `backend/.env`
3. `./.env` (repository root)
4. Defaults in `app/core/config.py`

`get_settings()` is `lru_cache`d, so settings are a process-wide singleton and
validation errors surface once at import rather than per request.

Nothing secret has a default. `EE_PROJECT` defaults to `None` and the service
refuses to initialise without it, rather than silently trying something wrong.

---

## Error handling

Domain errors subclass `CropSenseError`, which carries a `status_code`, a stable
machine-readable `code`, and a `details` dict. One handler in `main.py` renders
them all through the same envelope, logging 4xx at WARNING and 5xx at ERROR so
alerting can key off log level.

`EarthEngineAuthError` (503) is deliberately distinct from `EarthEngineError`
(502): the first says *fix your credentials*, the second says *retry or reduce
the request*. Conflating them makes a misconfiguration look like a transient
outage.

A catch-all `Exception` handler guarantees no stack trace reaches a client.

### Degraded start-up

The lifespan attempts Earth Engine initialisation and, by default, **logs a
failure without aborting**. The API boots, and `/health` reports HTTP 200 with
`status: "degraded"` plus a `remediation` array. Set `EE_FAIL_FAST=true` in
production to refuse traffic instead.

The reasoning: a developer who has not yet authenticated should get a running
server that tells them what to do, not a stack trace on startup.

### The credential pre-check

`gee_service.local_credentials_available()` checks the filesystem for a
credential file *before* calling `ee.Initialize`. When no file exists,
`ee.Initialize` falls back to `google.auth.default()`, which probes the GCE
metadata server and blocks for roughly ten seconds before failing. That turned
every `TestClient(app)` construction into a twelve-second stall and made the
suite unusable.

The pre-check is skipped when `EE_ALLOW_ADC_DISCOVERY=true`, which is required
when genuinely deploying on Google Cloud, where the runtime supplies credentials
with no file present.

---

## Testing strategy

115 backend unit tests use a stub Earth Engine service and need no credentials.
The separate opt-in integration test is marked `integration`; with live
credentials it exercises a small real Sentinel-2 analysis near Jalgaon,
Maharashtra.

* **`tests/conftest.py`** installs a `StubGEEService` as the module-level
  singleton in a session-scoped autouse fixture, covering the lifespan path that
  dependency overrides cannot reach. The `client` fixture additionally overrides
  `earth_engine_service` for the request path.
* **`StubGEEService.__getattr__`** returns a callable that raises
  `EarthEngineAuthError` for *any* method not explicitly stubbed. A route that
  forgets to handle the unavailable path therefore fails as a 503, not a 500 —
  the failure mode is a correct HTTP response rather than a crash.
* **`test_metrics.py`** exercises the pure numerics directly: percentages that
  must sum to 100, hectare conversion, OLS on degenerate inputs, warning
  thresholds at their boundaries.
* **`test_vegetation_model.py`** asserts on *wording*. The calibration note must
  still mention crop type and growth stage; the stress note must still say
  "potential" and "cannot diagnose"; no class description may name a disease.
  These are guard rails against a future edit quietly turning a screening tool
  into a diagnostic claim.
* **Integration tests** that hit the live API are marked `integration` and
  skipped unless `CROPSENSE_RUN_INTEGRATION=1`.

---

## Extension points

| To add | Touch |
| --- | --- |
| Another vegetation index (NDRE, NDMI, SAVI) | `ndvi_service.py` — add the band expression and vis params; `analysis_service.py` to include it in the response |
| A different satellite collection | `config.py` band/collection settings and `gee_service.build_sentinel2_collection()` |
| A new cloud-mask strategy | `CloudMaskMethod` enum plus a `_mask_with_*` method on `GEEService` |
| Result caching | A decorator around `AnalysisService` methods; the request models are hashable enough to key on |
| API authentication | A router-level dependency in `dependencies.py` |
| Field/AOI persistence | A new `app/db/` package and a `repositories` layer beside `services` |
| Batch or scheduled monitoring | A task queue calling `AnalysisService` directly — it has no HTTP dependency, which is the point of keeping FastAPI out of the service layer |

---

## Deliberate omissions

* **No database.** Nothing needs persisting yet; AOIs arrive with each request.
* **No caching.** Every request recomputes. Correct for interactive use, wasteful
  at scale, and the right thing to add first if this grows.
* **No API authentication.** Anyone who can reach the server can spend your Earth
  Engine quota. Required before public exposure.
* **No async Earth Engine calls.** The `earthengine-api` client is synchronous.
  Routes are `def`, not `async def`, so FastAPI runs them in a threadpool rather
  than blocking the event loop — which is the correct handling for a blocking
  client, and simpler than wrapping it.
