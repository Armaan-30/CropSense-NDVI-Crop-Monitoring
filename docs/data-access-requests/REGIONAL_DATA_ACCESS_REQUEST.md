# Requesting authorized Maharashtra field boundaries

Use this checklist when asking the Maharashtra Revenue / Land Records
Department, Agriculture Department, project partner, or state AgriStack team
for a pilot dataset/API. CropSense does not scrape citizen land-record portals.

## Request only the minimum data needed

- A pilot district/taluka and one named season.
- Stable pseudonymous field ID (no farmer name, Aadhaar, phone, or address).
- Field Polygon/MultiPolygon geometry in EPSG:4326, or a documented projection
  and conversion instructions.
- Cultivated area in hectares for the same season and the rule used to compute it.
- Crop type/growth-stage labels only where the farmer has consented and sharing
  is explicitly authorized.
- Dataset publication/release date, known gaps, update cadence, and a contact
  for corrections.
- Written license/terms stating whether storage, processing by Google Earth
  Engine, and map/result display in CropSense are permitted.
- Official current cultivated-area denominator for the same region/season,
  with the measure identified (net sown or gross cropped area), units, source,
  and as-of date.
- API documentation and scoped credentials if data is provided through an API;
  credentials must be stored outside source control.

The Government of India's 3 February 2026 Lok Sabha reply reports state-owned
AgriStack registries, geo-referenced map APIs, and consent-controlled data
exchange. Ask the state for the authorization and onboarding path; the reply
does not grant public access to those APIs.

## Official starting points

- For parcel-boundary availability and data-use authorization, contact the
  Office of the Settlement Commissioner and Director of Land Records,
  Maharashtra, Pune: `dlrmah.mah@nic.in`, +91 20 2605 0006 / 2605 0886.
  Ask them to route the request to the authorized AgriStack/Farmer Registry
  data custodian if that office does not issue the extract directly.
- For official cultivated-area statistics and a denominator source, contact
  the Commissionerate of Economics and Statistics, Maharashtra:
  `commissioner.es@maharashtra.gov.in`, +91 22 2202 0003. Specify district,
  taluka if available, crop season/year, the net-sown or gross-cropped area
  basis, and the publication/as-of date. The statewide office may redirect a
  district-level request to the relevant District Statistical Office.

These are contact routes to request authorization and data; they do not imply
that an export or API is available to this project. Do not send farmer personal
data by ordinary email. Use the department's approved secure channel if access
is granted.

## Data acceptance checks

Before processing, confirm:

1. The license/authorization covers the intended use and the project records
   its non-personal approval reference.
2. Field IDs are stable and unique; geometry records do not overlap in a way
   that double-counts cultivated hectares.
3. Each boundary is a valid closed Polygon/MultiPolygon and corresponds to the
   claimed cultivated-area figure.
4. The denominator and field areas use the same season, geography, and area
   definition.
5. Any crop labels used for threshold calibration are separate from the
   independent observations used to validate results.

## CropSense pilot manifest fields

Provide a GeoJSON `FeatureCollection` or GeoPackage layer. A GeoPackage layer
must declare its coordinate reference system; the runner transforms it to
EPSG:4326. Each feature must have these properties:

```json
{
  "field_id": "stable-pseudonymous-id",
  "cultivated_area_ha": 1.25,
  "crop_type": "optional, only if authorized",
  "season": "optional season label"
}
```

The geometry must be a Polygon or MultiPolygon. The pilot CLI checks the
GeoJSON structure, ring closure, ID uniqueness, and positive area. The
operator's explicit authorization/non-overlap confirmations are also required.

## Safe pilot command

After receiving an authorized manifest and current denominator, run from the
repository root with a small per-invocation cap (for example, five fields):

```powershell
backend/.venv/Scripts/python.exe scripts/run_regional_monitor.py `
  C:/path/to/authorized-pilot.gpkg `
  --layer "field_boundaries" `
  --region "district / taluka" `
  --season "season-year" `
  --dataset-name "authorized source name" `
  --dataset-release "source release or date" `
  --dataset-license "license reference" `
  --authorization-reference "non-personal approval reference" `
  --denominator-ha <official-hectares> `
  --denominator-basis net_sown `
  --denominator-source "official table/API and geography" `
  --denominator-as-of YYYY-MM-DD `
  --start-date YYYY-MM-DD `
  --end-date YYYY-MM-DD `
  --max-fields 5 `
  --target-fraction 1.0 `
  --authorized-data `
  --non-overlapping-boundaries
```

The CLI defaults to a 100% denominator target; this can be set explicitly with
`--target-fraction 1.0`. The first run prints a `run_id`. Re-run the same command and manifest with
`--run-id <that-id>` to process the next capped batch. Results and provenance
are written to the ignored local database `data/regional-monitoring.sqlite3`.
Do not schedule repeated runs until the pilot's compute use, imagery gaps, and
the desired update cadence have been reviewed.
