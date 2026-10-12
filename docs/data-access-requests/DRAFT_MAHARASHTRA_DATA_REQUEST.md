# Draft request for authorized CropSense pilot data

Use this as a starting draft for the Office of the Settlement Commissioner and
Director of Land Records, Maharashtra. Send it only through an official channel
and include your own identity/organization and purpose details. Do not attach
farmer personal records unless the department gives you an approved secure
transfer method.

**To:** `dlrmah.mah@nic.in`

**Subject:** Request for authorized, privacy-preserving farm-boundary data for an academic CropSense pilot

Dear Sir/Madam,

I am developing CropSense, an academic/internship project that uses Sentinel-2
satellite imagery and the Normalized Difference Vegetation Index (NDVI) to
monitor vegetation condition. I request guidance on the authorization process
for a small pilot using farm boundaries in **[district/taluka/village]** for
**[season and year]**.

If the department is able to provide or authorize a suitable dataset, the
minimum fields needed are:

- a stable pseudonymous field ID;
- Polygon/MultiPolygon farm boundary, preferably GeoPackage or GeoJSON, with
  coordinate reference system documented;
- cultivated hectares for the matching season and the area-calculation basis;
- crop/season metadata only where sharing is permitted and consented;
- dataset release/as-of date, license/terms, known coverage gaps, and update
  process.

The project does not need Aadhaar numbers, farmer names, phone numbers,
addresses, or ownership details. Please advise whether the data may be stored
in a local project database, processed by Google Earth Engine against
Sentinel-2 imagery, and displayed as field-level results in a non-public
dashboard. If those uses are not covered by the existing terms, please advise
the required consent, agreement, security review, or API onboarding steps.

Please also identify the official contact or process for obtaining a
matching cultivated-area denominator for the same geography and season, or
confirm whether this request should be sent separately to the Commissionerate
of Economics and Statistics.

I will not scrape public citizen portals or use data outside the permission
granted. I can provide a short project description, data-flow diagram, and
security details if required.

Thank you,

**[Your full name]**

**[College / internship program]**

**[Official email and phone]**

## Denominator request

Send a separate request to `commissioner.es@maharashtra.gov.in` asking for the
official cultivated-area measure for the same district/taluka and season.
Specify whether the project needs net-sown area (unique land over a reference
period) or gross-cropped area (crop area that may count a parcel more than
once), and request its source, release date, and applicable geography.

Official contact listings: [Maharashtra Land Records](https://emojni.mahabhumi.gov.in/citizensite/Contactus.aspx)
and [Commissionerate of Economics and Statistics](https://www.mahades.maharashtra.gov.in/contactDES.do?type=C).
