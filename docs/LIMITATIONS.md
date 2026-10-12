# Assumptions and limitations

This document states plainly what CropSense does and does not establish. It
exists because remote-sensing dashboards very easily *look* more authoritative
than they are.

---

## 1. The central limitation: NDVI is not a diagnosis

NDVI measures the contrast between near-infrared and red reflectance. Healthy
green vegetation reflects strongly in the NIR and absorbs strongly in the red,
so NDVI rises with the amount of green, photosynthetically active canopy.

That makes NDVI a well-established proxy for **vegetation vigour and biomass**.
It does not make it a diagnostic instrument.

**A decline in NDVI is equally consistent with all of the following:**

* Harvest, mowing or grazing
* Tillage, or a change in soil moisture at the surface
* Lodging after wind or heavy rain
* Waterlogging or flooding
* Drought or irrigation failure
* Nutrient deficiency
* Pest damage
* Fungal, bacterial or viral disease
* Normal end-of-season senescence
* Residual, unmasked cloud shadow
* A change in sun-sensor geometry between overpasses

CropSense cannot distinguish among these. Where the API flags an area, it says
"**potential vegetation stress requiring ground verification**", and that wording
is enforced by unit tests in `backend/tests/test_vegetation_model.py`.

**Specifically: this project does not detect crop disease.** No band ratio from
Sentinel-2's 10–60 m multispectral bands can identify a pathogen. Disease
identification requires in-field inspection, laboratory diagnosis, or at minimum
hyperspectral or very-high-resolution imagery combined with a validated,
crop-specific and pathogen-specific model. None of that is present here.

---

## 2. No accuracy or validation metrics are reported

You will not find an accuracy figure, F1 score, kappa coefficient, RMSE against
ground truth, or citation-backed performance claim anywhere in this project.

That is deliberate. Establishing such a metric requires paired ground
observations over the same fields and dates, which this project does not have.
Any number presented would be fabricated. If you later collect ground data, the
threshold-calibration procedure in
[THRESHOLD_CALIBRATION.md](THRESHOLD_CALIBRATION.md) is the place to record what
you find.

---

## 3. Classification thresholds are conventions, not measurements

The five health classes are produced by binning continuous NDVI at four
boundaries, defaulting to `0.2, 0.4, 0.6, 0.8`. These are **generic starting
points in wide informal use**, not derived constants.

Absolute NDVI for a healthy crop varies with:

* **Crop type** — maize, wheat, rice, cotton and sugarcane differ substantially
  at equivalent health.
* **Growth stage** — the single largest factor. A healthy wheat field at
  tillering may sit near 0.35; the same field at booting near 0.85. A fixed
  threshold labels the first "low" and the second "very healthy" when both are
  perfectly healthy for their stage.
* **Canopy cover and row spacing** — partial cover mixes soil into every pixel.
* **Soil background** — dark, wet or organic soils raise NDVI at equal canopy
  cover; bright, sandy or calcareous soils lower it.
* **Region, season and latitude** — through illumination geometry and
  atmospheric path.
* **Residual atmospheric effects** — L2A correction is good, not perfect.

Treat the class labels as *relative* zoning within one field on one date. Use
them to find the worst 10% of a field, not to assert that a field is
"unhealthy".

**NDVI also saturates.** Above roughly 0.8 it responds weakly to further
increases in biomass, so it discriminates poorly among dense canopies. A field
reading 0.85 and one reading 0.92 are not reliably distinguishable in condition.

---

## 4. Sensor and data limitations

| Limitation | Consequence |
| --- | --- |
| **10 m pixels** | Roughly a 100 m² ground cell. Sub-pixel features — individual plants, narrow strips, field edges — are mixed with their surroundings. Edge pixels of small fields contain road, bund or hedge. |
| **~5-day revisit** (two-satellite constellation) | The finest achievable temporal resolution. Cloud loss makes the effective interval much longer; in monsoon conditions a whole month can yield nothing usable. |
| **Cloud masking is imperfect** | Cloud Score+ is the best available general-purpose mask but misses thin cirrus and semi-transparent haze, and over-masks bright surfaces. Residual contamination biases NDVI downward; over-masking silently shrinks the sample. |
| **Cloud shadow** | Detected by Cloud Score+ and SCL, missed entirely by QA60. Shadowed vegetation reads as depressed NDVI — a very common false-stress source. |
| **Cloud Score+ coverage begins 2017-06-27** | Earlier windows fall back to SCL masking. The response `warnings` array says so when this happens. |
| **Sentinel-2 archive begins 2015-06** (L2A more limited early) | No analysis of earlier seasons is possible. |
| **Surface-reflectance correction** | L2A is Sen2Cor output. Aerosol and water-vapour retrievals fail sometimes, particularly over bright or heterogeneous surfaces. |
| **Geometric registration** | Sub-pixel but not zero. Per-pixel change detection between dates carries a small co-registration error, worst at field edges. |

---

## 5. Processing assumptions made by this implementation

Each of these is a defensible choice, not the only correct one.

1. **Median compositing by default.** Robust against residual cloud, but it
   averages across the window — a 30-day composite is not a snapshot, and a real
   short-lived stress event can be smoothed away. `most_recent` is available for
   current-state questions.
2. **Cloud-masked pixels are excluded, never zero-filled.** This is the honest
   choice; the cost is that statistics come from a variable subset of the AOI.
   Always read `valid_pixel_fraction` — a mean over 3% of a field is not a field
   mean, and the API emits a warning when coverage is low.
3. **Scene-level cloud filter applied before per-pixel masking.** Cheap and
   effective, but a scene 40% clouded elsewhere and perfectly clear over your
   field is discarded at `cloud_threshold=30`. Raise the threshold when working
   with small AOIs.
4. **10 m analysis scale.** Native for B4/B8, so no resampling of the inputs.
   Large AOIs may need a coarser `scale_m` to stay within Earth Engine's pixel
   budget, which changes the reported areas slightly.
5. **Class bins are `[lower, upper)`.** A pixel exactly on a threshold falls in
   the higher class.
6. **Areas are computed from pixel counts at the analysis scale** via
   `ee.Image.pixelArea`, so a reported hectare figure is quantised to the pixel
   grid and depends on `scale_m`.
7. **Point AOIs are buffered into circles** (`buffer_m`, default 250 m). A circle
   is not a field boundary; draw a polygon for anything quantitative.
8. **The linear trend is ordinary least squares on retained points.** Vegetation
   through a season is not linear. Over a full phenological cycle the slope is
   close to meaningless. The response includes `r_squared`, `n_points` and an
   `interpretation` string; read the chart, not just the slope.
9. **Change detection compares only pixels cloud-free in both windows.** This
   keeps the comparison honest but means `comparable_area_fraction` can be well
   below 1, and the declined-area percentage is a share of *comparable* area,
   not of the field.
10. **`reduceRegion` has a 10 M pixel budget** (`REDUCE_REGION_MAX_PIXELS`).
    Earth Engine subsamples beyond it. AOI area is capped at 2500 km² by
    default for this reason.

---

## 6. Operational limitations

* **Tile URLs are short-lived.** `getMapId()` returns signed, session-scoped
  endpoints. They expire; the frontend must re-request analysis rather than
  persist them. They carry no credential, which is why they are safe to send to
  a browser.
* **Earth Engine quotas apply.** Concurrent-request and compute limits are
  Google's, not configurable here. The high-volume endpoint is used because it
  suits many small interactive requests.
* **No caching layer.** Every request recomputes. Fine for interactive use,
  wasteful at scale.
* **No authentication on the API.** Anyone who can reach the server can spend
  your Earth Engine quota. Add auth before exposing it publicly.
* **Free Earth Engine access is for noncommercial and research use.** Commercial
  use requires a paid plan. That is Google's licensing, and it is your
  responsibility to comply.

---

## 7. Appropriate and inappropriate use

**Reasonable uses**

* Finding the relatively worst-performing zones within a field, to direct
  scouting.
* Tracking a field's NDVI trajectory across a season and comparing it to the
  same field in a previous season.
* Screening many fields to decide which to visit first.
* Confirming that a known event (harvest, flood, hail) is visible in the imagery.

**Uses this project does not support**

* Diagnosing a disease, or naming a pathogen.
* Certifying a field as healthy or unhealthy for insurance, subsidy, compliance
  or legal purposes.
* Yield prediction. NDVI correlates with yield, but a calibrated model — with
  its own validation — is a separate piece of work.
* Comparing absolute NDVI across different crops, or across growth stages,
  without stage-aware calibration.
* Any decision where being wrong is expensive and the finding has not been
  checked on the ground.

---

## 8. What would be needed to go further

If this project were extended toward genuine stress attribution:

1. **Ground truth.** Dated, geolocated field observations. Nothing below this
   line matters without it.
2. **Crop and stage awareness.** A crop mask plus a phenology model, so
   thresholds move with the growth stage instead of being fixed.
3. **Additional indices.** NDRE and the chlorophyll red-edge indices (B5/B6/B7)
   are more sensitive than NDVI at high biomass, where NDVI saturates. NDMI
   (B8A/B11) responds to canopy water. NDWI and SAVI address water and soil
   background respectively.
4. **A within-field anomaly baseline** — comparing a pixel to its own history
   and to its neighbours in the same field is far more informative than
   comparing it to a global threshold.
5. **Weather data**, to separate water stress from other causes.
6. **Validation, reported honestly**, including the cases where it fails.

---

## Attribution

Contains modified Copernicus Sentinel data, processed by the European Space
Agency, accessed through Google Earth Engine. Cloud Score+ is produced by
Google. Sentinel-2 data are provided under the Copernicus open-data licence.
