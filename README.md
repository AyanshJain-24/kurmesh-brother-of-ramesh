# KURMESH V1

KURMESH is a maritime decision-support system. It currently contains Phase 1 infrastructure and the Phase 2 application foundation: a React health dashboard, Flask API, PostGIS persistence schema, authentication/authorization primitives, audit-event creation, and human route review/approval controls. It contains no connected environmental provider, ML, routing, simulation-worker, or frontend domain workflow implementation.

## Start locally

1. Install Docker Desktop and ensure it is running.
2. Copy `.env.example` to `.env`.
3. Replace `POSTGRES_PASSWORD` and the matching password in `DATABASE_URL` in `.env`. Set `AUTH_SECRET` to a unique random value of at least 32 characters. The API refuses to start without it.
4. From the repository root, run:

```sh
docker compose up --build
```

Open `http://localhost`. The UI requests `GET /api/v1/health` through Nginx; no browser-side API host configuration is necessary in Compose.

## Validate

```sh
docker compose config
docker compose up --build -d
curl http://localhost/api/v1/health
docker compose ps
docker compose logs --tail=100 backend worker
docker compose down
```

The API checks PostgreSQL connectivity, the installed PostGIS extension, and Redis reachability. `GET /api/v1/health/live` is dependency-free; `GET /api/v1/health/ready` returns 503 until required dependencies are ready.

## Local non-container frontend build

```sh
cd frontend
npm ci
npm run build
```

## Backend tests and migrations

```sh
docker compose run --rm backend pytest
docker compose exec backend alembic current
```

The backend container applies Alembic migrations before serving traffic. The initial migration uses explicit Alembic operations and creates only KURMESH tables and indexes. Its downgrade drops only those objects; it does not remove the PostGIS extension or unrelated database objects.

Run backend checks locally from `backend/`:

```sh
pytest -q
python -m compileall app migrations
alembic upgrade --sql head
alembic downgrade --sql base
```

The clean-PostGIS integration tests run only when `KURMESH_INTEGRATION_DATABASE_URL` names a disposable database. They reset that database's `public` schema, so never point it at operational data.

## Phase 2 API foundation

All API routes are under `/api/v1`. Health routes are public. The domain API has request-scoped SQLAlchemy sessions; domain endpoints require Bearer authentication unless otherwise indicated. Account creation creates no privileged role. Roles must be assigned through an approved administrative process outside this API foundation.

Mission mutations require the mission owner or an `admin` role. Mission state changes use the explicit state graph in the API. Route approval requires an `operator` or `admin`, an existing human review, and a different reviewer and approver. Audit events are created by mutations and have no write, update, or delete API endpoints.

## Phase 3A API

Phase 3A completes the authentication, user-profile, and mission API foundation. Register with `POST /api/v1/auth/register` using `email`, a password of at least 12 characters, and `full_name`; registration assigns the non-privileged `user` role. Authenticate with `POST /api/v1/auth/login`, then supply the returned token as `Authorization: Bearer <token>`.

`GET /api/v1/auth/me` and `GET /api/v1/users/me` return the authenticated safe user profile. A user may retrieve their own `/api/v1/users/<uuid>` profile; `admin` may retrieve other profiles. Mission CRUD remains under `/api/v1/missions`; list responses accept `page` and `page_size` (maximum 100) and include pagination metadata. A referenced vessel must exist.

Phase 3B does not implement ML, environmental providers, routing algorithms, simulation execution, or frontend domain workflows.

## Phase 3B-1 metadata APIs

Authenticated callers can persist and retrieve explicitly supplied metadata at `/api/v1/environment/sources`, `/api/v1/environment/observations`, `/api/v1/models`, `/api/v1/models/<model_id>/artifacts`, and `/api/v1/predictions`. Observation locations use `{ "longitude": ..., "latitude": ... }` and are stored as SRID 4326 points. Prediction creation records only a submitted persistence request (`PENDING`, `FAILED`, or `MODEL_UNAVAILABLE`); it never runs inference or creates outputs.

## Phase 3B-2 governed routing workflow

Mission owners or `admin` may manage submitted route candidates and operational route records at `/missions/<mission_id>/route-candidates` and `/missions/<mission_id>/routes`. Geometry is validated SRID-4326 GeoJSON `LineString` data; these endpoints never calculate a route.

Reviews (`POST /routes/<route_id>/reviews`) and approvals (`POST /routes/<route_id>/approvals`) are separate operator/admin actions. A mission owner cannot act as reviewer or approver without admin authority, an approved review is required before approval, and the reviewer cannot approve the same route. Creating or reviewing a route never approves it; only an explicit approval record may transition it to `APPROVED` or `REJECTED`.

Mission-scoped alerts are available at `/missions/<mission_id>/alerts` with acknowledgement at `/alerts/<alert_id>/acknowledgement`. Operators/admins may record explicitly supplied provenance at `/provenance`; only admins may list it. Workflow mutations create append-oriented audit events, which have no mutation endpoint.

## Environment and safety

Use `.env.example` only as a template; never commit `.env`. The provided password is deliberately a placeholder and fails Compose interpolation until replaced. Production requires a secrets manager, TLS/reverse proxy configuration, restricted CORS origins, backups, and authenticated API domains in later phases.

## Phase 4A environmental provider architecture

Phase 4A adds an architecture boundary only; it includes no real external provider, network request, environmental value, ML inference, routing calculation, or new Flask endpoint. Existing `/api/v1/environment/*` APIs remain manual metadata APIs and retain their contracts.

Future workers or services use this flow:

```
External provider -> provider adapter -> normalized observation -> validation/status/provenance -> ingestion service -> existing environment tables
```

Provider adapters live under `backend/app/environment/providers.py`. An adapter implements `EnvironmentalProviderAdapter`, declares the domains it supports (`sea_ice`, `weather`, or `ocean_conditions`), and is responsible only for its provider's authentication, request construction, and response parsing. It returns `NormalizedEnvironmentalObservation` objects; adapters must not import Flask routes, SQLAlchemy models, repository code, ML, or routing modules.

The normalized observation carries observation type, source observation time, retrieval time, optional WGS84 location, provider/product/source reference, optional checksum, status, values/units, metadata, and provenance details. The ingestion service stores only data-bearing `LIVE`, `STALE`, or `DEGRADED` observations and creates a linked append-only provenance record using the existing `environment_sources`, `environment_observations`, and `provenance_records` schema. `UNAVAILABLE` and `ERROR` outcomes intentionally contain no values and are not persisted as observations, preventing a failure diagnostic from becoming fake environmental data.

Status semantics are explicit:

- `LIVE`: provider data is available and current according to the adapter's documented freshness rule.
- `STALE`: genuine provider data is available but outside that freshness rule.
- `DEGRADED`: genuine provider data is available with a documented limitation (for example, partial coverage); the limitation belongs in provenance/metadata.
- `UNAVAILABLE`: the provider is disabled, no adapter is registered, its domain is unsupported, or it returned no data. No observation values are invented.
- `ERROR`: an adapter raised while requesting or parsing. The normalized outcome preserves a safe diagnostic code and exception type without exposing secrets; a future worker may log operational detail separately.

Configuration is opt-in and disabled by default. `KURMESH_ENVIRONMENT_PROVIDERS` lists future adapter names; each name may use `KURMESH_ENVIRONMENT_PROVIDER_<NAME>_ENABLED`, `_ENDPOINT`, `_API_KEY`, and `_TIMEOUT_SECONDS`. Enabled providers require an absolute HTTP(S) endpoint. Secrets belong in deployment environment/secrets management, never source control. Compose forwards the registry and default timeout; when Phase 4B introduces a named adapter, its explicitly named endpoint/credential variables must also be forwarded to the backend/worker services.

To add a provider in a later phase: implement and test its adapter against mocked provider payloads, register it in the worker/service composition root, configure its opt-in variables, define freshness/degradation rules, and invoke `EnvironmentalObservationIngestionService` inside a transaction. Do not place provider parsing in a Flask route and do not treat mock payloads as real data.

## Phase 4B-1 NOAA/NSIDC Antarctic sea ice

The opt-in `noaa_nsidc_g10016` adapter retrieves one daily Antarctic file from the official NOAA/NSIDC Near-Real-Time Climate Data Record of Passive Microwave Sea Ice Concentration, **G10016 Version 4**. The source is NetCDF4, daily, 25 km resolution, and uses the NSIDC South Polar Stereographic grid (**EPSG:3412**). It reads the documented `cdr_seaice_conc` variable and optional interpolation/quality flag variables; no weather, ocean, ML, or routing data is introduced.

The adapter accepts a requested WGS84 Antarctic point, transforms it to EPSG:3412 to select the nearest source grid cell, then transforms that selected cell back to WGS84 for the existing PostGIS geometry. It never treats `x`/`y` metre offsets as longitude/latitude. Provenance retains G10016, version 4, source URL, SHA-256 of the downloaded file, the CF variable name/metadata, source CRS, and original projected coordinates.

Set `KURMESH_ENVIRONMENT_PROVIDERS=noaa_nsidc_g10016`, enable `KURMESH_ENVIRONMENT_PROVIDER_NOAA_NSIDC_G10016_ENABLED`, and configure its official endpoint, timeout, freshness-hours, lookback-days, and bounded valid-cell fallback radius from `.env.example`. No API key is used. The adapter tries only the requested day and the configured number of prior days, so it does not download a historical collection. `LIVE` means source time is within `FRESHNESS_HOURS`; older genuine data is `STALE`; interpolation flags or a recorded nearest-valid-cell fallback create `DEGRADED`; absent daily files or no valid cell inside the configured radius become `UNAVAILABLE`; and network, malformed-file, missing-variable, invalid-value, or CRS failures become `ERROR` without fabricated/persisted data.

Unit tests use only a tiny generated, clearly test-only G10016-format NetCDF fixture. To make a deliberate live request, set `KURMESH_RUN_LIVE_PROVIDER_TESTS=true` alongside enabled configuration and run `pytest -m live_provider`; normal test runs skip it.

## Phase 4B-2 NOAA GFS weather forecasts

The opt-in `noaa_gfs` adapter requests a small, variable-filtered window from NOAA/NCEP NOMADS GFS 0.25-degree GRIB2 forecasts. It provides 10 m wind (u/v components, derived speed and meteorological direction), 2 m air temperature (normalised to °C), and mean sea-level pressure (normalised to hPa). These are forecasts: `observed_at` is the GFS model cycle and `valid_to` is the selected forecast valid time; retrieval time remains separate.

Set `KURMESH_ENVIRONMENT_PROVIDERS=noaa_gfs`, enable `KURMESH_ENVIRONMENT_PROVIDER_NOAA_GFS_ENABLED`, and configure `KURMESH_ENVIRONMENT_PROVIDER_NOAA_GFS_ENDPOINT=https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl`. Docker Compose supplies that same public NOMADS endpoint by default, but non-Compose deployments must configure it explicitly. A six-hour freshness threshold is the default. The adapter selects the nearest grid cell containing all required values using great-circle distance. A configurable, bounded fallback uses `DEGRADED`; a request without a complete valid cell inside that radius is `UNAVAILABLE`. Provenance records the GFS run, forecast hour and valid time, requested and selected coordinates, source/normalised units, fallback information, and source checksum. The live test is opt-in only when provider name, enabled state, endpoint, and `KURMESH_RUN_LIVE_PROVIDER_TESTS=true` are all configured. For Docker Compose: `docker compose run --rm -e KURMESH_ENVIRONMENT_PROVIDERS=noaa_gfs -e KURMESH_ENVIRONMENT_PROVIDER_NOAA_GFS_ENABLED=true -e KURMESH_RUN_LIVE_PROVIDER_TESTS=true backend pytest -q -rs -m live_provider`.

## Phase 4B-3 Copernicus Marine ocean conditions

The opt-in `copernicus_marine_ocean` adapter uses the official Copernicus Marine Toolbox `subset()` API to request bounded subsets of `cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i` (`uo`, `vo`) and `cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i` (`thetao`) in product `GLOBAL_ANALYSISFORECAST_PHY_001_024`. It selects the shallowest shared valid depth and returns current components, speed, and direction (the direction the current flows toward, clockwise from north), plus potential temperature normalised to °C. The endpoint is a required configured Copernicus service reference; the Toolbox performs the authenticated data access.

Enable it with `KURMESH_ENVIRONMENT_PROVIDERS=copernicus_marine_ocean`, provider configuration from `.env.example`, and deployment-only `COPERNICUSMARINE_SERVICE_USERNAME` / `COPERNICUSMARINE_SERVICE_PASSWORD`. Credentials are never stored in source, logs, or provenance. Synthetic tests never contact Copernicus. Live access must be explicitly enabled and supplied with credentials. A bounded nearest-valid fallback is `DEGRADED`; lack of a valid shared location/depth is `UNAVAILABLE` without fabricated values.

## Repository layout

- `frontend/`: React/Vite health dashboard and API health integration.
- `backend/`: Flask API, explicit Alembic migration, PostGIS models, auth foundation, dependency health probes, structured logging, and Celery configuration.
- `workers/`: reserved for task-domain modules as worker behavior grows.
- `database/`: reserved; Alembic migrations live in `backend/migrations/`.
- `ml/`, `routing/`, `data/`, `models/`: reserved; no connected providers, artifacts, or fabricated outputs exist here.
- `tests/`: cross-service and end-to-end tests added in later phases.
