# CropSense setup

This document covers local and deployment configuration. Earth Engine access
requires a registered Google Cloud project and credentials for an authorized
Google identity. Check the current machine's setup with
`scripts/check_setup.py`; do not commit local credentials or `.env` files.

---

## 1. Prerequisites

* **Python 3.11+**. GeoPackage ingestion requires Fiona; the runtime dependency
  is installed on Python versions below 3.14. GeoJSON ingestion does not require
  Fiona. The Docker backend uses Python 3.12.
* **Node.js 22.18+** for Vite 8 and the frontend utility tests.
* **A Google account** — needed for Earth Engine. Free for noncommercial and
  research use.

---

## 2. Register for Google Earth Engine (manual, one-time)

Earth Engine's v1 API requires a **Google Cloud project** that is registered for
Earth Engine use. There is no API for this; it is a web form.

1. **Create or choose a Cloud project.**
   <https://console.cloud.google.com/projectcreate>
   Note the *project ID* (e.g. `cropsense-471203`), not the display name.

2. **Enable the Earth Engine API on that project.**
   <https://console.cloud.google.com/apis/library/earthengine.googleapis.com>
   Click **Enable**.

3. **Register the project for Earth Engine.**
   <https://code.earthengine.google.com/register>
   Choose *Unpaid usage* → *Academia & Research* (or whichever applies), then
   select the project from step 1. Approval is usually immediate.

You now have a project ID. Everything else in this document depends on it.

---

## 3. Authenticate (manual, one-time)

Pick **one** of the two options.

### Option A — user credentials (recommended for local development)

Run this in the backend virtual environment. It opens a browser, asks you to
sign in, and writes a refresh token to disk. The `earthengine` CLI ships with
`earthengine-api`, which is already installed in `backend/.venv`:

```bash
./backend/.venv/Scripts/earthengine.exe authenticate
```

On macOS/Linux:

```bash
./backend/.venv/bin/earthengine authenticate
```

The token is written to:

* Windows — `C:\Users\<you>\.config\earthengine\credentials`
* macOS/Linux — `~/.config/earthengine/credentials`

This file is **outside the repository** and is never committed.

If the browser returns `ERR_CONNECTION_REFUSED` at `localhost:8085`, the
temporary callback listener was not reachable. Keep the authentication command
running until it reports that the token was saved; the Google consent page
alone does not create a local credential. If that callback still fails, use
Earth Engine's notebook flow, which returns a code for the CLI and avoids the
localhost callback entirely:

```bash
./backend/.venv/Scripts/earthengine.exe authenticate --auth_mode=notebook
```

Open the printed URL, sign in with the Google account registered for Earth
Engine, copy the resulting authorization code back into the same terminal,
and wait for the CLI to confirm the token was saved. This mode may require
creating/selecting an authentication project in the Earth Engine Notebook
Authenticator. Then verify setup with:

```powershell
./backend/.venv/Scripts/python.exe scripts/check_setup.py --live
```

### Option B — service account (recommended for hosted deployments and CI)

1. Create a service account in your Cloud project:
   <https://console.cloud.google.com/iam-admin/serviceaccounts>
2. Grant it the **Earth Engine Resource Viewer** role.
3. **Register the service-account email itself** at
   <https://code.earthengine.google.com/register>.
   Registering the *project* is not sufficient — the service account needs its
   own registration, and this is the step people most often miss.
4. Create a JSON key and download it. Store it **outside** the repository, or
   under `secrets/` (git-ignored).
5. Set these in `.env`:

   ```dotenv
   EE_USE_LOCAL_CREDENTIALS=false
   EE_SERVICE_ACCOUNT_EMAIL=cropsense-ee@your-project.iam.gserviceaccount.com
   EE_SERVICE_ACCOUNT_KEY_FILE=/absolute/path/to/key.json
   ```

   Or supply the key inline as one line of JSON via
   `EE_SERVICE_ACCOUNT_KEY_JSON=` — useful with a secret manager, since it needs
   no writable filesystem.

---

## 4. Create your `.env`

```bash
cp .env.example .env
```

Then edit `.env` and set at minimum:

```dotenv
EE_PROJECT=your-gcp-project-id
```

`.env.example` documents every other variable inline. `.env` is git-ignored;
`.env.example` contains no real values and is committed.

Settings resolve in this order, first match winning:

1. Real process environment variables
2. `backend/.env`
3. `./.env` (repository root)
4. Defaults in `backend/app/core/config.py`

---

## 5. Verify

```bash
./backend/.venv/Scripts/python.exe scripts/check_setup.py --live
```

Without `--live` it does filesystem and configuration checks only (no network).
With `--live` it performs two real Earth Engine round trips: a trivial
arithmetic evaluation, then a tightly bounded Sentinel-2 catalogue query. Exit
code 0 means ready.

The same information is available from the running API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/system/gee-test
```

When Earth Engine is unavailable, `/health` returns HTTP 200 with
`"status": "degraded"` and a `remediation` array of concrete next steps, and
`/api/system/gee-test` returns 503 with the same guidance. The API deliberately
boots in degraded mode rather than crashing, so you can see *why* it is broken.
Set `EE_FAIL_FAST=true` in production to invert that.

---

## 6. Run the backend

```bash
cd backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

* Interactive API docs — <http://localhost:8000/docs>
* OpenAPI schema — <http://localhost:8000/openapi.json>

---

## 7. Run the checks

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests -q
```

```bash
cd backend && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy
```

The unit tests never contact Earth Engine — a session-scoped fixture in
`tests/conftest.py` swaps in a stub client, so the suite runs in under a second
with no credentials. Tests that need the live API are marked `integration` and
skipped unless `CROPSENSE_RUN_INTEGRATION=1`:

PowerShell (from the repository root):

```powershell
$env:CROPSENSE_RUN_INTEGRATION = "1"
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q -m integration
Remove-Item Env:CROPSENSE_RUN_INTEGRATION
```

Bash (from the repository root):

```bash
CROPSENSE_RUN_INTEGRATION=1 ./backend/.venv/Scripts/python.exe -m pytest backend/tests -q -m integration
```

The live smoke test posts a small field and 30-day window to
`POST /api/ndvi/analyze`. It uses SCL masking and 20 m statistics to keep the
request bounded. It is skipped in the default offline suite.

Frontend checks and local development:

```bash
cd frontend && npm test && npm run lint && npm run build
cd frontend && npm run dev
```

## Docker Compose

With Docker Desktop installed and the repository-root `.env` configured, use
the local Earth Engine credential overlay. It mounts your credential directory
read-only:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local-ee.yml up --build -d
```

Open <http://localhost:8080>. The frontend container proxies API requests to
the backend on the private Compose network. The base stack without the overlay
starts in degraded mode if no service-account credentials are configured.

For hosted deployments, use the service-account settings from option B rather
than mounting a developer's user credentials. Neither image contains credential
files.

---

## Troubleshooting

**`EEException: Earth Engine client library not initialized`**
`EE_PROJECT` is unset, or the project is not registered. Revisit steps 2 and 4.

**`Caller does not have required permission to use project`**
The Earth Engine API is not enabled on the project, or the project/service
account is not registered. Step 2 and step 3 option B item 3.

**`No Earth Engine credentials found`**
No credential file on disk. Run `earthengine authenticate` (step 3A). The
backend checks for the file *before* calling `ee.Initialize`, because the
underlying Application Default Credentials fallback probes the GCE metadata
server and blocks for roughly ten seconds before failing. If you are actually
deploying on Google Cloud (Cloud Run, GCE, GKE) where the runtime supplies
credentials with no file present, set `EE_ALLOW_ADC_DISCOVERY=true`.

**OAuth browser shows `ERR_CONNECTION_REFUSED` at `localhost:8085`**
This is the local callback server used by the CLI, not an internet connectivity
failure. The authentication process must still be running while you approve
access. If the callback cannot connect, complete authentication with
`earthengine authenticate --auth_mode=notebook` as described above. A successful
Google sign-in is not enough: verify that the CLI says it saved the token and
that `scripts/check_setup.py --live` reports successful Earth Engine access.

**No imagery returned for a valid AOI and date range**
Genuinely possible, and not a bug: Sentinel-2 revisit is ~5 days, and a
monsoon month can have no usable scene at all. The API returns HTTP 404 with
`code: "no_imagery"` and suggests widening the window or raising
`cloud_threshold`. It never substitutes synthetic data.

**Cloud Score+ appears to do nothing before mid-2017**
Correct. `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` starts 2017-06-27. For
earlier dates the backend falls back to `SCL` masking and says so in the
response `warnings`.
