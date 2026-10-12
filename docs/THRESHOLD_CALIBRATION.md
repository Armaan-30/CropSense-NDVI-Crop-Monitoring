# Calibrating the NDVI classification thresholds

The defaults are `0.2, 0.4, 0.6, 0.8`. They are **generic starting points**, in
wide informal use but not derived from measurement. This document explains how
to replace them with values that mean something for your fields.

Read [LIMITATIONS.md](LIMITATIONS.md) first if you have not. In particular: no
threshold set turns NDVI into a diagnosis.

---

## Why fixed thresholds mislead

The single largest confounder is **growth stage**.

Consider a healthy wheat field observed through one season. Its NDVI trajectory
is roughly:

```
NDVI
 0.9 |                    ,--.
 0.8 |                 ,-'    `.
 0.7 |               ,'          `.
 0.6 |             ,'              `.
 0.5 |           ,'                  `.
 0.4 |         ,'                      `.
 0.3 |      ,-'                          `-.
 0.2 |  ,--'                                `--.
 0.1 |-'                                        `----
     +------------------------------------------------
       emergence  tillering  booting  grain fill  ripening
```

Against fixed thresholds, this **entirely healthy** field is classified as:

| Stage | Typical NDVI | Fixed-threshold label |
| --- | --- | --- |
| Emergence | 0.15 | Very low / non-vegetated |
| Tillering | 0.35 | Low |
| Stem elongation | 0.55 | Moderate |
| Booting / heading | 0.85 | Very healthy |
| Grain fill | 0.70 | Healthy |
| Ripening (normal senescence) | 0.30 | Low |

Four of six observations of a healthy crop read as sub-healthy. The classifier
is not broken; it is being asked a question it cannot answer without knowing the
growth stage.

**The practical consequence:** use the classes to compare *within* one field on
*one date*, and use the time series to compare a field against itself. Do not
read the class label as a verdict on the crop.

---

## Method 1 — Relative zoning (no ground data required)

The most defensible thing you can do without field observations. Instead of
asking "is this field healthy", ask "which parts of this field are worst".

1. Run `POST /api/ndvi/analyze` for your field and date.
2. Read `statistics.p10`, `statistics.median` and `statistics.p90` from the
   response.
3. Set thresholds from that distribution, for example:

   ```
   t0 = p10
   t1 = (p10 + median) / 2
   t2 = median
   t3 = p90
   ```

4. Send them back in `options.ndvi_class_thresholds`.

The five classes now mean "worst decile / below average / average / above
average / best decile *of this field on this date*". That statement is true
regardless of crop, stage or region, which is exactly why it is useful.

Recompute per date. The thresholds move with the crop, which is the point.

---

## Method 2 — Ground-truth calibration (the real thing)

Requires field work. This is what would let you make an absolute claim.

### Collect

For each observation record:

* GPS coordinates (ideally the centre of a homogeneous patch at least 30 m
  across, so it covers a clean 3×3 block of 10 m pixels)
* Date, within ±2 days of a Sentinel-2 overpass with the field cloud-free
* Crop type and **growth stage** (BBCH or an equivalent scale)
* An agronomist's condition rating on a fixed scale, e.g. 1–5
* Anything that would confound the reading: recent irrigation, tillage,
  spraying, visible pest or disease damage, waterlogging

Aim for at least 30 observations per crop **per growth-stage band**, spread
across the full condition range. Fewer than that and you are fitting noise.

### Extract

For each observation, get NDVI at that point on that date. A 30 m buffer around
the point works well — it averages a 3×3 pixel block and tolerates a few metres
of GPS error:

```json
{
  "aoi": {"type": "Point", "coordinates": [75.806, 30.904]},
  "buffer_m": 30,
  "start_date": "2024-01-14",
  "end_date": "2024-01-16",
  "cloud_threshold": 20
}
```

Use `statistics.mean` from the response. Discard any observation whose
`valid_pixel_fraction` is below about 0.8 — partial cloud makes the point
unusable.

### Derive

Group observations by crop and growth-stage band. Within each group, sort by
NDVI and find the values that best separate adjacent condition ratings. A simple,
transparent approach: take the midpoint between the mean NDVI of adjacent rating
classes.

Record what you did and what the data was, including sample size per class.
Sample sizes are what tell a later reader whether to trust the boundaries.

### Validate

Hold out roughly 30% of the observations, or use k-fold cross-validation. Report
the agreement you actually measured, including the classes it gets wrong. A
threshold set that works well at booting and badly at tillering is a useful
result — record it rather than hiding it.

### Deploy

Per deployment, in `.env`:

```dotenv
NDVI_CLASS_THRESHOLDS=0.18,0.36,0.58,0.76
```

Per request, when thresholds vary by crop or stage:

```json
{ "options": { "ndvi_class_thresholds": [0.18, 0.36, 0.58, 0.76] } }
```

Every response reports `health.thresholds` and `health.thresholds_source`
(`"request"` or `"server_default"`), so results stay traceable to the thresholds
that produced them.

---

## Method 3 — Regional literature values

If published, peer-reviewed values exist for your crop, region and stage, use
them — and cite them where you record your configuration, including the
conditions the study covered.

Do not transplant thresholds from a study in a different climate, on a different
crop, at a different growth stage, and present them as validated for your
fields. That is the most common way a dashboard like this becomes confidently
wrong.

**This project ships no such citations**, because none have been verified for
any particular deployment. The defaults are conventions, and the code says so.

---

## Rules of thumb, offered as starting points only

Treat these as hypotheses to test, not as values to trust.

**By crop, at peak vegetative growth, healthy:**

| Crop | Approximate peak NDVI |
| --- | --- |
| Maize | 0.80 – 0.90 |
| Sugarcane | 0.80 – 0.90 |
| Rice (flooded, full canopy) | 0.70 – 0.85 |
| Wheat | 0.75 – 0.90 |
| Cotton | 0.70 – 0.85 |
| Soybean | 0.75 – 0.88 |
| Pulses / chickpea | 0.60 – 0.80 |

**By surface type, useful for sanity checks:**

| Surface | Approximate NDVI |
| --- | --- |
| Open water | −0.3 – 0.0 |
| Cloud (unmasked) | around 0.0 |
| Bare soil, dry | 0.10 – 0.20 |
| Bare soil, wet | 0.05 – 0.15 |
| Crop residue / stubble | 0.15 – 0.25 |
| Sparse or emerging crop | 0.20 – 0.40 |
| Dense healthy canopy | 0.70 – 0.95 |

If your field reads 0.05 in mid-season, suspect the data before the crop:
unmasked cloud, water, or a mis-drawn AOI over a road or pond.

---

## The decline threshold

`NDVI_DECLINE_THRESHOLD` (default `0.15`) sets how large a same-pixel drop
between two periods gets flagged as a potential stress area.

Calibrate it against your own false-positive tolerance:

* **Lower it (0.08 – 0.12)** to catch subtle changes, accepting more false
  positives from residual cloud shadow and normal variation.
* **Raise it (0.20 – 0.25)** to flag only unambiguous changes, accepting that
  early or mild stress is missed.

Two things to account for before tightening or loosening it:

1. **Phenology is not stress.** Comparing peak vegetative growth against
   ripening produces a large, entirely normal decline across the whole field.
   Compare like stage with like stage — for example the same calendar window in
   two seasons — or interpret whole-field decline as expected.
2. **Harvest looks like catastrophic stress.** A harvested field shows a
   near-total NDVI collapse. Know your field operations before reading a flag as
   a problem.

---

## Recording your calibration

Whatever you derive, write it down next to the numbers: crop, stage band, region,
season, sample size, who rated condition and on what scale, measured agreement,
and the date the calibration was performed. Thresholds without that context are
indistinguishable from the arbitrary defaults they replaced.

## Evaluating a candidate threshold set

Fill in [`calibration_observations_template.csv`](calibration_observations_template.csv)
with observed crop condition labels and NDVI values extracted for matching
dates. Select thresholds using a separate calibration subset. Then evaluate
once on an independent holdout CSV:

```powershell
python scripts/evaluate_thresholds.py path\to\held-out-observations.csv `
  --thresholds 0.18,0.36,0.58,0.76 --independent-validation
```

The tool reports per-class precision, recall and F1, overall accuracy, macro-F1,
and a confusion matrix for that file only. It refuses to report scores without
the explicit holdout confirmation. Do not tune boundaries on this validation
file and then report the same scores as independent validation. Record crop,
growth stage and field coverage separately; pooled scores can hide failures in
particular stages or locations. The template is intentionally blank: this
repository contains no fabricated farm observations or accuracy results.
