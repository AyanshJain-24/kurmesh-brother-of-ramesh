# KURMESH Phase 5F: Immutable Artifact and Provenance Packaging

## Scope and status

This offline packaging review neither trained nor tuned a model. It did not
change a production API, routing, provider, frontend, backend, database,
authorization, Docker, or CI component. Raw NetCDF and CSV inputs are not in
this repository or in either artifact. No commit was created.

**Phase 5J ML adapter integration: NO-GO.** The Phase 5F portability gate
passes, but compatibility between historical G02202 V6 feature inputs and the
operational G10016 product remains an independent, unresolved prerequisite.

## 1. Original portability problem and correction

The original Phase 5D sea-ice companion metadata referenced a machine-local
`%TEMP%` manifest. That made its provenance non-portable even though the model
JSON itself could be loaded elsewhere.

Each new package is a JSON envelope with schema version `1`. It preserves the
Phase 5D `model` object exactly and stores only repository-relative provenance:

- `data/manifests/phase5b_sea_ice_manifest.json` or
  `data/manifests/phase5b_iceberg_manifest.json`;
- `docs/ml/PHASE_5C_PREPROCESSING.md`, version `phase5c-v1`;
- dataset product/version, manifest SHA-256, feature-schema version, target and
  horizon, chronological splits/counts, selected hyperparameters, package
  versions, timestamp, deterministic seed state, and offline-only status.

There are no `%TEMP%` references, Windows absolute paths, raw-data filenames,
credentials, tokens, passwords, or embedded source observations in either
package.

## 2. Immutable inventory

| Package | SHA-256 | Model / dimensions | Referenced manifest SHA-256 |
| --- | --- | --- | --- |
| `sea_ice_ridge.portable.json` | `e3303e64c16d437207de32ae231e731c3bb9bc43af527d3f103e745a611b6ab9` | `ridge_closed_form_standardized`; 9 features / 1 target | `454efce2a144566fb024bae2a3591616d047aa3e2297327aa73769828b23ea51` |
| `iceberg_ridge.portable.json` | `8da49e83b0c7b9c54c6fd62cf235eb2e8bc8d10ebb78bf0254c4943c4673ac0f` | `ridge_closed_form_standardized`; 7 features / 2 targets | `4d951aa18e0346aa1f00e1ecd0610fb53bdc383ed37d0adf6bc88e6ca99ba1c6` |

The repackaging operation checked model-object equality against the Phase 5D
JSON before writing either envelope; it did not fit or transform coefficients,
train-only means/scales, alpha, feature order, or target order.

## 3. Clean portability test

On 2026-09-25, a new temporary directory outside Git was created and populated
with only the two portable package JSON files, the two referenced manifests,
and the Phase 5C preprocessing contract. The original Phase 5D training and
artifact directory was not supplied to, read by, or required by the test.

| Check | Sea ice | Iceberg |
| --- | --- | --- |
| Package JSON/schema and deserialization | PASS | PASS |
| Ridge type / ordered feature schema / target schema | PASS | PASS |
| Coefficient dimensions and finite model parameters | PASS | PASS |
| Manifest path resolution and exact SHA-256 match | PASS | PASS |
| Preprocessing-contract reference resolves | PASS | PASS |
| No `%TEMP%` or absolute Windows path | PASS | PASS |
| No raw dataset or secret/credential embedded | PASS | PASS |
| Original Phase 5D artifact directory required | NO | NO |

The deterministic prediction-only smoke test used existing real held-out data
outside the clean package folder. The sea-ice package produced finite `(16, 1)`
predictions for the 2024-06-26 target date. The iceberg package produced a
finite `(1, 2)` projected-displacement prediction for track `a23a`, target
date 2015-07-03. Neither operation retrained a model or evaluated/changed
reported Phase 5D metrics.

## 4. Tests and limitations

Focused tests cover deterministic loading, feature/target dimensions,
manifest-hash metadata, model-object preservation during package creation, and
rejection of machine-local provenance. The package test is implemented in
`ml/packaging/phase5f_portability_test.py`.

Portability here means the artifacts can be copied with their declared
metadata, not that they are operational inputs. The packages remain offline
experiment artifacts. Before any separately authorized adapter work, G10016 to
G02202 V6 feature compatibility, a bounded inference/provenance contract,
runtime dependency packaging, and the applicable human-in-the-loop review must
be completed.
