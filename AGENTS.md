# KURMESH Project Rules

- KURMESH is human-in-the-loop decision support. Never allow ML, routing, or workers to approve or execute a route.
- Never fabricate environmental data, ML predictions, confidence, provenance, live timestamps, route scores, or operational status.
- Use explicit availability states (`LIVE`, `STALE`, `UNAVAILABLE`, `ERROR`, `DEGRADED`, `MODEL_UNAVAILABLE`) and retain provenance.
- All API routes are under `/api/v1`; validate inputs and use safe errors. Mutations require authentication and authorization when introduced.
- Database schema changes go through Alembic migrations. Keep audit records append-only.
- Do not claim Docker, CI, data providers, or ML works without executing and recording the appropriate verification.
