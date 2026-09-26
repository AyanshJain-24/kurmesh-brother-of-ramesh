# KURMESH Phase 5E: Offline Artifact and Metric Review

## Scope and decision

This is an offline review of the Phase 5D artifacts and recorded held-out
metrics. It did not train, tune, alter, register, or integrate a model. It did
not modify any production API, provider, routing, frontend, database, or
authorization component.

**Phase 5J ML adapter integration: NO-GO.** Artifact integrity and offline
reproducibility pass, but operational input compatibility, a portable provenance
bundle, an explicit inference contract, and separate authorization for
production-adjacent integration are still required.

## 1. Artifact inventory and integrity

| Artifact | Format / model | SHA-256 verification | Feature / target dimensions |
| --- | --- | --- | --- |
| `%TEMP%/kurmesh-phase5d/artifacts/sea_ice_ridge.json` | JSON, `ridge_closed_form_standardized` | `e76f8ec44ab1a254ed9518359338dc892d03c2ade72e9694ee8cca9801c4c36b` — exact match | 9 / 1 |
| `%TEMP%/kurmesh-phase5d/artifacts/iceberg_ridge.json` | JSON, `ridge_closed_form_standardized` | `292b8991ef675b0609447a6b2f993e2675eeb0a790d442225cd8e6ef067035e0` — exact match | 7 / 2 |

Both JSON payloads contain only model type, alpha, ordered feature/target names,
train-only feature mean/scale, target mean, and coefficients. Neither embeds
raw NetCDF/CSV data, credentials, tokens, passwords, or an absolute filesystem
path. The accompanying metadata files carry the provenance and status
`OFFLINE_EXPERIMENT_ONLY`.

## 2. Metadata review against the frozen contracts

### Sea ice

The artifact and paired metadata agree with Phases 5C, 5C.1, and 5D:

- G02202 V6 Southern 2021–2024 strict dataset ID;
- nine ordered features: SIC lags 0/1/2/3/7 days, EPSG:3412 x/y, seasonal
  sine/cosine;
- same-cell decoded SIC target at +7 days and a seven-day horizon;
- QA=0, spatial interpolation=0, temporal interpolation=0, ocean mask=50,
  and fill value 255 exclusion;
- chronological train/validation/test dates and sample counts
  16,086,664 / 1,651,690 / 3,791,025;
- alpha 0.1 after validation selection; Python 3.12.14, NumPy 2.5.3, and
  h5py 3.15.1; no random seed because the closed-form fit is deterministic.

### Icebergs

The artifact and metadata agree with the Phase 5C/5C.1/5D contract:

- BYU/NIC V3 strict dataset ID;
- seven ordered past-only features: current projected x/y, prior dx/dy,
  normalized prior longitude delta, seasonal sine/cosine;
- two-target EPSG:3412 dx/dy displacement at +24 hours;
- splits/counts 189,892 / 49,245 / 59,444;
- alpha 10.0 after validation selection; Python 3.12.14, NumPy 2.5.3, and
  pyproj 3.8.0; no random seed.

No semantic metadata mismatch was found. One portability gap remains: the
sea-ice metadata's dataset manifest reference is
`%TEMP%/kurmesh-phase5c1/phase5c1_sea_ice_local_manifest.json`. It is a
provenance pointer, not an inference dependency, but it is machine-local and
must be replaced by a portable immutable manifest reference before any later
adapter work. Both artifacts should also gain an explicit preprocessing-contract
document/code revision reference before integration.

## 3. Clean-load and inference smoke tests

Each artifact deserialized successfully into the repository's
`StandardizedRidge` object. Expected feature counts and target dimensions were
validated before prediction.

A deterministic held-out smoke evaluation then used the loaded artifacts only:

- sea ice: first three chronological test blocks, 55,939 real examples;
- iceberg: first 1,000 chronological test examples.

The smoke pass produced finite predictions and metrics with the expected target
dimensions. It did not fit a transformer or estimator, and target fields were
not introduced into features.

## 4. Full test-metric reproduction

The review reloaded the serialized coefficients/scalers and re-evaluated the
existing chronological test examples. It used absolute tolerance `1e-12` for
floating-point comparison with Phase 5D. All checked MAE, RMSE, and sample
counts reproduced with absolute difference **0.0**.

| Dataset / model | Reproduced test n | MAE | RMSE |
| --- | ---: | --- | --- |
| Sea-ice persistence | 3,791,025 | 0.0633180578 | 0.1079545906 |
| Sea-ice Ridge | 3,791,025 | 0.0689521181 | 0.1036217210 |
| Iceberg constant velocity | 59,444 | dx 2642.782639 m; dy 2255.981957 m | dx 25530.483635 m; dy 12432.674619 m |
| Iceberg Ridge | 59,444 | dx 2393.072121 m; dy 2385.794148 m | dx 16450.443795 m; dy 8742.112555 m |

The review-only command is [phase5e_artifact_review.py](../../ml/review/phase5e_artifact_review.py).
Its temporary report is `%TEMP%/kurmesh-phase5e/phase5e_local_review.json`.

## 5. Neutral metric relationships

- For sea ice, persistence has lower MAE; Ridge has lower RMSE.
- For icebergs, Ridge has lower dx MAE; constant velocity has lower dy MAE;
  Ridge has lower dx RMSE and dy RMSE.

These relationships are reported separately; this review does not create a
combined score, winner, confidence value, or operational-performance claim.

## 6. Portability, limitations, and integration prerequisites

The model JSON files themselves are portable coefficient/normalization payloads
and have no training-only absolute filesystem dependency. Their paired metadata
does have the local `%TEMP%` sea-ice manifest reference noted above. Raw inputs
are not embedded, which is correct but means later use must provide separately
verified input provenance.

Before a separately authorized Phase 5J, all of the following are required:

1. Replace local-only manifest pointers with portable, immutable dataset and
   preprocessing-contract references.
2. Verify G02202 V6 historical features against any intended operational input
   product; that compatibility remains unknown.
3. Define an explicit non-production inference I/O, provenance, availability,
   and error contract without changing routing behavior.
4. Review artifact storage, dependency locking, security, human-in-the-loop
   presentation, and model lifecycle policy.
5. Obtain explicit authorization for adapter work. No route may be approved or
   executed by a model.

The artifacts remain offline experiment outputs only. No model was integrated,
no secret was added, and no commit was made.
