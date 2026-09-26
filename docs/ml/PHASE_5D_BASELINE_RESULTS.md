# KURMESH Phase 5D: Offline Real-Data Baseline Results

## Scope and status

This is the first completed, offline-only baseline experiment. It used the
validated real NOAA/NSIDC G02202 V6 and BYU/NIC V3.0 data described in Phases
5A–5C.1. It does not authorize production inference, routing integration,
automated decisions, confidence scores, or any operational claim.

All raw data, generated blocks, result JSON, and model artifacts remain in
local temporary directories outside Git.

## Dataset provenance and preprocessing contract

### Sea ice

- Dataset: NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice
  Concentration, G02202 V6, Southern Hemisphere, 2021–2024.
- Corpus validation: 1,461 daily files; no missing, corrupt, duplicate, or
  grid-inconsistent files. See [Phase 5C.1](PHASE_5C1_VALIDATION.md).
- Input: native EPSG:3412 25 km source cell; SIC lags t, t−1, t−2, t−3, t−7;
  x/y; and issue-date day-of-year sine/cosine.
- Target: decoded same-cell SIC fraction at t+7 days.
- Eligibility: raw SIC 0–100 scaled by 0.01, excluding fill 255; QA=0;
  spatial interpolation=0; temporal interpolation=0; surface mask=50 Ocean.
  Fill values were excluded, never changed to zero.
- Chronological target-date splits: train 2021-01-15–2023-10-24; validation
  2023-11-08–2024-05-28; test 2024-06-12–2024-12-31. Feature windows crossing
  a split or embargo boundary were excluded.

### Icebergs

- Dataset: BYU/NIC Antarctic Iceberg Tracking Database V3.0; local archive
  checksum and schema are in `data/manifests/phase5b_iceberg_manifest.json`.
- Input: current projected x/y, prior observed 24-hour dx/dy, normalized prior
  longitude difference, and issue-date day-of-year sine/cosine.
- Target: observed t→t+24-hour dx/dy in EPSG:3412.
- Parser: malformed dates excluded; prior/issue/target observed-position bits
  required; both segments require calendar and `date_gap` one day; track/date
  duplicates excluded; longitude differences normalized to [-180, 180).
- Splits: train 1992-01-03–2011-05-02; validation 2011-05-06–2015-06-27; test
  2015-07-01–2019-08-14, with the Phase 5C embargo and no cross-boundary
  window.

## Baselines and model selection

Sea-ice persistence predicts `SIC(t+7) = SIC(t)`. The sea-ice candidate is a
standardized closed-form Ridge regression over the nine permitted features.

Iceberg constant velocity predicts the next dx/dy from the preceding observed
24-hour dx/dy. The candidate is a multi-output standardized closed-form Ridge
regression over the seven permitted features.

All feature means/scales and sufficient statistics were fitted from train
examples only. Ridge alpha selection used validation only: candidates 0.1, 1.0,
and 10.0; the selected alpha was 0.1 for sea ice and 10.0 for icebergs. The
test set was evaluated once after selection.

## Actual sample counts and test metrics

### Sea ice

| Experiment | Test examples | MAE (SIC fraction) | RMSE (SIC fraction) | Mean signed error |
| --- | ---: | ---: | ---: | ---: |
| Persistence | 3,791,025 | 0.063318 | 0.107955 | 0.014743 |
| Ridge | 3,791,025 | 0.068952 | 0.103622 | -0.001393 |

Training/validation/test sample counts were 16,086,664 / 1,651,690 /
3,791,025. Validation MAE for alpha 0.1/1.0/10.0 was
0.087353856 / 0.087353858 / 0.087353874 respectively.

### Icebergs

| Experiment | Test examples | dx MAE m | dy MAE m | dx RMSE m | dy RMSE m | Mean absolute magnitude error m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Constant velocity | 59,444 | 2,642.783 | 2,255.982 | 25,530.484 | 12,432.675 | 2,830.789 |
| Ridge | 59,444 | 2,393.072 | 2,385.794 | 16,450.444 | 8,742.113 | 3,351.521 |

Training/validation/test sample counts were 189,892 / 49,245 / 59,444.
Validation mean component MAE for alpha 0.1/1.0/10.0 was
2,725.998987 / 2,725.998889 / 2,725.997919 m.

These are measured held-out experiment results, not operational-performance or
production-readiness claims.

## Artifacts and reproducibility

The artifacts are local-only and explicitly marked `OFFLINE_EXPERIMENT_ONLY`.
They contain model coefficients, train-only feature scaling, ordered feature and
target definitions, dataset references, split dates, hyperparameters, library
versions, timestamp, and artifact SHA-256. They do not contain raw data.

| Artifact | Local path | SHA-256 |
| --- | --- | --- |
| Sea-ice Ridge | `%TEMP%/kurmesh-phase5d/artifacts/sea_ice_ridge.json` | `e76f8ec44ab1a254ed9518359338dc892d03c2ade72e9694ee8cca9801c4c36b` |
| Iceberg Ridge | `%TEMP%/kurmesh-phase5d/artifacts/iceberg_ridge.json` | `292b8991ef675b0609447a6b2f993e2675eeb0a790d442225cd8e6ef067035e0` |

Run metadata live beside each artifact as `*.metadata.json`. Reproduce from the
repository root with the existing local corpus/dependencies:

```powershell
python -m ml.training.phase5d_baselines `
  --sea-ice-dir "$env:TEMP\kurmesh-phase5c1\g02202_v6_south_daily_2021_2024" `
  --iceberg-dir "$env:TEMP\kurmesh-phase5b-iceberg\stats_v3\stats" `
  --artifact-dir "$env:TEMP\kurmesh-phase5d\artifacts" `
  --report "$env:TEMP\kurmesh-phase5d\phase5d_local_results.json" `
  --dependency-path "$env:TEMP\kurmesh-phase5b-python" `
  --dependency-path "$env:TEMP\kurmesh-phase5c1-python"
```

## Failed run

One initial run failed before any model fitting because the reader attempted to
access `surface_type_mask` at the NetCDF root. The field is in
`cdr_supplementary`; the reader was corrected to use group-aware lookup. The
successful run above used the unchanged validated policy and corpus.

## Limitations and next-phase recommendation

- These are historical, offline experiments only; no current operational input
  compatibility or inference service has been established.
- The strict sea-ice filter deliberately excludes many cells. Iceberg tracks
  remain historical and contain repeated zero displacement and occasional large
  observed displacement.
- No confidence score was created.

**Phase 5E recommendation: proceed only with a separate review of the real
artifacts, their held-out metrics, and a non-operational inference/provenance
design. Do not integrate either artifact with routing or production APIs.**
