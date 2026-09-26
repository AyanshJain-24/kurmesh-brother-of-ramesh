# Public demo deployment

KURMESH is a decision-support application.  A deployment is not complete until
the frontend, API, database, and bootstrap command are independently running.
The public demo seed creates no environmental observations, ML predictions,
route candidates, routes, reviews, or approvals.

## Required cloud services

1. A static Vercel project with `frontend/` as its root directory.
2. A public HTTPS Flask API built from `backend/Dockerfile`.
3. Managed PostgreSQL with PostGIS enabled. The API deployment identity needs
   permission to apply Alembic migrations.
4. Managed Redis when workers or readiness checks are enabled.
5. An optional worker deployment built from `backend/Dockerfile` with the
   existing Celery command.

The frontend does not proxy production API calls. Configure the API URL at
Vercel build time and allow the exact Vercel origin in the API CORS setting.

## Required production environment

### Vercel

`VITE_API_BASE_URL=https://<public-api-host>/api/v1`

### API

- `DATABASE_URL` — managed PostgreSQL/PostGIS SQLAlchemy URL.
- `REDIS_URL` — managed Redis URL.
- `AUTH_SECRET` — unique secret of at least 32 characters.
- `CORS_ORIGINS` — comma-separated exact browser origins, for example
  `https://<project>.vercel.app`.
- `KURMESH_DEMO_SEED=true` — explicitly enables the public-demo bootstrap.
- `KURMESH_DEMO_EMAIL` — judge-facing demo account email.
- `KURMESH_DEMO_PASSWORD` — judge-facing demo password, at least 12 characters.
- `KURMESH_DEMO_FULL_NAME` — optional display name.

Provider credentials and `KURMESH_DEMO_ICEBERG_MODEL_ARTIFACT_PATH` remain
optional. If they are absent, the application must show its existing
`UNAVAILABLE` or `MODEL_UNAVAILABLE` states rather than invented values.

Never store any of these values in source control, Vercel project files, or
documentation.

## Deploy

1. Provision PostgreSQL/PostGIS and Redis, then configure the API variables.
2. Deploy the API image from `backend/Dockerfile`. Its startup command applies
   migrations, executes `python -m app.demo_seed`, then starts Gunicorn. The
   seed is a no-op unless `KURMESH_DEMO_SEED=true`.
3. In Vercel, set the project root to `frontend`, configure
   `VITE_API_BASE_URL`, and deploy. `frontend/vercel.json` rewrites direct SPA
   navigation such as `/missions` and `/routes` to `index.html`.
4. Copy the demo credentials to the judge briefing through a secure channel.

For a platform that requires an explicit API start command, use:

```sh
alembic upgrade head && python -m app.demo_seed && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - --error-logfile - app.wsgi:app
```

## Bootstrap behaviour

When enabled, the seed creates or reuses one user, **KURMESH Research Vessel**,
and **Antarctic Research Mission**. The vessel declares
`cruising_speed_knots: 12.0`; the mission has Antarctic origin/destination
points and initially enters `ANALYZING`. If a judge has already generated
candidates, a later seed run preserves the route workflow state. It records one
append-only `DEMO_BOOTSTRAPPED` audit event and does not duplicate the seeded
user, vessel, or mission.

## Map behaviour

The Operational Map uses MapLibre's embedded neutral style; it requires no map
token or external tile service. “Operational map unavailable” therefore means
the browser could not initialize MapLibre/WebGL. Its fallback intentionally
draws no layers. Candidate lines appear only when the API returned real route
geometry.

## Judge acceptance check

Open the deployed Vercel URL, sign in with the configured demo account, open
the seeded mission, verify its coordinates/state, and explicitly select
**Generate Route Options**. Then use **Routes** to select a returned candidate.
Review and approval continue to require their existing authorized human roles;
the seed never grants an automatic approval or creates route data.
