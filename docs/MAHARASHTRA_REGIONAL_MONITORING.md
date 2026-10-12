# Maharashtra regional farm monitoring

## What works today

CropSense retrieves Sentinel-2 Level-2A imagery for user-selected AOIs and
computes NDVI, health-class areas, time series, and change screening. The
FastAPI route supports one AOI per request, with a configured maximum AOI of
2,500 km². The Docker deployment has been exercised on a small field near
Jalgaon. These are real imagery results, but they do not constitute statewide
or multi-farm monitoring.

You can use the dashboard immediately without importing a farm dataset: draw
your own AOI in Maharashtra, paste a boundary you are entitled to use, or click
**Use Maharashtra demo area** to run a small example rectangle near Jalgaon.
The demo rectangle is only for exercising the live workflow; it is not a
surveyed parcel and its NDVI must not be interpreted as a specific farm's
condition. The Docker deployment has been verified end to end against live
Sentinel-2 for this approximately 1.15 ha rectangle.

Sentinel-2 has a nominal five-day revisit and 10 m red/NIR bands. This means
imagery can cover Maharashtra; it does not provide cadastral farm polygons,
crop identity, or guaranteed cloud-free observations every five days. Cloudy
periods must be reported as gaps or composited over a wider window.

## Coverage target: cultivated hectares

The configured target is **100%** of the declared cultivated-hectare
denominator (`--target-fraction 1.0`). The report distinguishes processed area
from cloud-valid observed area: a 100% processing goal does not imply cloud-free
imagery for every field or date. No statewide 100% operational coverage has
been demonstrated.

The target is measured as cloud-valid cultivated hectares divided by an
official cultivated-area denominator for the same region and season. Report
attempted/processed hectares separately from hectares with usable cloud-free
pixels. This avoids counting a cloudy or failed field as an observed result.
The field dataset must have stable, unique IDs, source-provided cultivated
area, and non-overlapping boundaries; otherwise the hectare total can be
double-counted. The denominator must state its source and as-of date.

For the statewide target, use an official season-specific cultivated-area
total. District/season crop statistics on India's Open Government Data portal
are published in hectares, but are aggregate totals and do not supply field
geometries. Confirm which area measure (net sown area or gross cropped area)
matches the intended season and avoid mixing them.

## Authorized data source path

The Government of India's February 2026 Lok Sabha reply reports that
Maharashtra's AgriStack registries are maintained by the states, that more than
41,000 geo-referenced maps had been digitized, and that APIs for those maps had
been shared. It also states that data exchanges use controlled, token-based
access and that farmers control sharing of their data with authorized entities
for specific purposes. This does **not** mean those APIs are publicly callable
or that CropSense currently has access.

Request a pilot extract/API authorization from the Maharashtra Revenue / Land
Records Department or Agriculture Department and ask them to coordinate with
the state Farmer Registry/AgriStack team. Request only fields needed for this
project: stable pseudonymous field ID, Polygon/MultiPolygon boundary in
EPSG:4326, cultivated area in hectares, crop/season if consented, dataset
release/as-of date, and explicit license/use terms. Do not request Aadhaar,
owner names, phone numbers, or other direct personal identifiers. The official
Mahabhumi site explicitly cautions against unauthorized duplication or misuse
of its records; do not scrape BhuNaksha or citizen portals.

The public Maharashtra State Data Bank can help identify official aggregate
area statistics, but its surfaced net-sown value is from 2019-20 and is too old
to silently use as a current seasonal denominator. Obtain the latest suitable
official denominator for the same season and geography, then record its source
and publication date.

## Recommended rollout

1. **Secure a permitted boundary source.** Request a licensed/authorized
   GeoPackage, GeoJSON, or equivalent from the farm owner, project partner, or
   Maharashtra land-record authority. The runner accepts GeoPackage (Fiona;
   select its vector layer with `--layer`) and GeoJSON. Require stable parcel IDs and, if
   available, crop type and season. Keep personal landholder details out of
   Earth Engine requests.
2. **Define the target and pilot.** Select one taluka, measure total usable
   parcel area/count, and pick a small representative pilot. Validate boundary
   alignment and imagery availability before increasing area.
3. **Run the bounded pilot worker.** `scripts/run_regional_monitor.py` validates
   an authorized GeoJSON/GeoPackage manifest, runs fields serially in capped batches,
   stores per-field results and Sentinel-2 provenance in a SQLite checkpoint,
   and can resume a partial run. It reports processed area separately from
   cloud-valid area. It is an operator-run pilot tool, not a distributed queue
   or statewide production scheduler; do not run it on a state-sized dataset.
4. **Pilot and measure compute.** The regional runner now records each
   successful field's server processing time and reports the sample count,
   total, mean, and maximum in its SQLite-backed report. These are wall-clock
   processing measurements, not Earth Engine compute units (EECUs). Track real
   EECU usage separately in the Google Cloud project before expanding. The
   Community Tier is currently documented as 150 EECU-hours per month; actual
   compute per field must be measured on this workflow. Do not launch a
   Maharashtra-wide run from the dashboard.
5. **Expand incrementally.** Increase by taluka or another agreed unit only
   after a pilot fits the user's quota and observation/update requirements.
   Report coverage as processed eligible hectares/parcels divided by the
   defined denominator, with stale, cloudy, failed, and unprocessed records
   shown separately.
6. **Validate crop interpretation.** Collect date-matched field condition
   observations by crop and growth stage. Keep threshold selection data
   separate from validation data; see
   [THRESHOLD_CALIBRATION.md](THRESHOLD_CALIBRATION.md). NDVI remains a
   vegetation-vigour indicator and cannot confirm a disease or its cause.

## Current blockers for regional monitoring

This repository does not contain the authorized field dataset, the current
official cultivated-hectare denominator, department/API authorization, or
date-matched crop-condition observations. A bounded serial pilot runner and
checkpoint/report store now exist, but they have not been run on real parcel
boundaries. Its opt-in live integration test has verified the analysis route
on a small Maharashtra AOI, not the multi-farm runner. There is no automatic
update cadence, distributed job queue,
multi-user storage, or demonstrated 100%-of-state production service. No
statewide run should start until source authorization, denominator, pilot
resource use, and the operator cadence are agreed.

## Sources

- [Google Earth Engine Sentinel-2 catalog](https://developers.google.com/earth-engine/datasets/catalog/sentinel-2/)
- [Maharashtra Mahabhumi land-record portal](https://mahabhumi.gov.in/Mahabhumilink/MainDashboard/MainDashboard)
- [Maharashtra BhuNaksha portal](https://mahabhunakasha.mahabhumi.gov.in/27/index.jsp)
- [Government of India Lok Sabha reply on Farmer IDs, Digital Crop Survey, and geo-referenced maps (3 Feb 2026)](https://sansad.in/getFile/loksabhaquestions/annex/187/AU490_505h8i.pdf?source=pqals)
- [Maharashtra Farmer Registry (AgriStack)](https://mhfr.agristack.gov.in/)
- [Maharashtra State Data Bank](https://mahasdb.maharashtra.gov.in/maagCmpIndia.do)
- [India Open Government Data: district/season crop production statistics](https://www.data.gov.in/catalog/district-wise-season-wise-crop-production-statistics-0)
- [Earth Engine noncommercial tiers and EECU quotas](https://developers.google.com/earth-engine/guides/noncommercial_tiers)
- [Earth Engine usage quotas and batch task limits](https://developers.google.com/earth-engine/guides/usage)
