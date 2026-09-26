# KURMESH Phase 5G: G10016 to G02202 Operational Feature-Contract Audit

## Scope and decision

This is an offline audit. It did not retrain, tune, alter, or integrate a model,
modify the G10016 provider, production APIs, routing, or dependencies. Raw
NetCDF remains outside Git. No model prediction or commit was created.

**Overall Phase 5J recommendation: NO_GO.** The underlying products have an
exactly aligned grid, but the existing provider output cannot produce or prove
the strict, same-cell, five-date, quality-qualified feature window required by
the trained Ridge artifact without unsupported new orchestration.

## 1. Trained sea-ice Ridge contract

Portable artifact: sea_ice_ridge.portable.json; SHA-256
e3303e64c16d437207de32ae231e731c3bb9bc43af527d3f103e745a611b6ab9.
It is a standardized closed-form Ridge model (alpha 0.1) with train-only
serialized feature means/scales. No new scaler may be fitted.

| Order | Feature | Unit/domain | Meaning |
| ---: | --- | --- | --- |
| 1–5 | sic_lag_0_days, sic_lag_1_days, sic_lag_2_days, sic_lag_3_days, sic_lag_7_days | decoded SIC fraction 0–1 | G02202 V6 cdr_seaice_conc at issue t, t−1, t−2, t−3, t−7 at one same native cell |
| 6–7 | x_m, y_m | EPSG:3412 metres | fixed native 25 km cell centre |
| 8–9 | day_of_year_sin, day_of_year_cos | unitless [-1, 1] | sine/cosine from the **issue observation date** |

Target: separate sic_t_plus_7_days, the decoded same-cell SIC fraction at t+7
days. Training used final G02202 V6 Southern 2021–2024 on the fixed 332×316
EPSG:3412 grid. The artifact references data/manifests/phase5b_sea_ice_manifest.json,
SHA-256 454efce2a144566fb024bae2a3591616d047aa3e2297327aa73769828b23ea51,
and the Phase 5C contract.

Every historical input/label passed raw SIC range 0–100, fill-255 exclusion,
qa_flag=0, spatial interpolation flag 0, temporal interpolation flag 0, and
surface_type_mask=50 (Ocean). Missing values were excluded, never turned into
zero. At issue time only past inputs can be checked; the +7-day value is the
prediction target.

## 2. G10016 V4 operational/provider contract

Primary code evidence:
[noaa_nsidc_g10016.py](../../backend/app/environment/noaa_nsidc_g10016.py) and
[test_noaa_nsidc_g10016.py](../../backend/tests/test_noaa_nsidc_g10016.py).

The provider identifies NOAA/NSIDC Near-Real-Time CDR Passive Microwave Sea Ice
Concentration, G10016 Version 4. It downloads one daily NetCDF file,
CF-decodes/mask-scales it, transforms an Antarctic WGS84 point to EPSG:3412,
and selects one nearest grid cell. It returns:

- value={concentration: decoded finite fraction} and source units;
- observed_at from NetCDF time (falling back to filename date) and separate
  retrieved_at;
- selected x/y in metres, request/selected coordinates, source URL, SHA-256,
  dataset ID/version, CRS, and fallback details in provenance;
- optional QA, spatial-flag, and temporal-flag fields in provenance.

It does **not** return raw SIC, original-cell fill status, surface_type_mask,
a complete grid, or a five-date feature window. A missing requested value can
be replaced by a bounded nearest valid cell; that output is DEGRADED and
records its new selected x/y. QA non-zero does not itself cause DEGRADED;
optional flags can be None.

LIVE means the source time is within configured freshness; genuine older data
is STALE. Non-zero spatial/temporal flags or fallback are DEGRADED; unavailable
files/no bounded valid cell are UNAVAILABLE; network, parse, variable,
invalid-value, or CRS failures are ERROR.

### Actual official sample

The official [G10016 V4 user guide](https://nsidc.org/sites/default/files/documents/user-guide/g10016-v004-userguide.pdf)
documents daily NRT data, recent-three-month retention, preliminary status,
AMSR2 input, cdr_seaice_conc, raw 0–100/scale 0.01/fill 255, daily Southern
shape [1, 332, 316], and EPSG:3412. It documents QA/interpolation fields and
surface_type_mask in cdr_supplementary, with Ocean=50.

This actual file was retrieved temporarily and not stored in Git:

https://noaadata.apps.nsidc.org/NOAA/G10016_V4/south/daily/2026/sic_pss25_20260923_am2_icdr_v04r00.nc

It was 404,067 bytes; SHA-256:
470aa998f6a1996bf467722560f6222d113551c4844146334c74156ee1f909eb.
Inspection found SIC and all three flags at root, and
cdr_supplementary/surface_type_mask. SIC was uint8 (1, 332, 316), units 1,
standard name sea_ice_area_fraction, valid raw range 0–100, scale 0.01, add
offset 0, and fill 255. Its time was 20,719 days since 1970-01-01, matching
2026-09-23. Its x/y extents were −3,937,500…3,937,500 m and
4,337,500…−3,937,500 m; CRS metadata specified EPSG:3412.

The actual sampled G10016 x/y hashes were
c82b5ad53e3404a93a13556ee2f9def0c619fe5d3fd3a797cd05794f7909d535 and
14063bef7b727ed29f86b7ee723793d5ad4fa8c40c7ce7d7a95e236d2be6e3e2.
They exactly equal the x/y arrays in an existing validated 2024-01-01 G02202
V6 file. The G10016 guide's Table 12 says 331 Southern y pixels while its
daily-variable table and this actual file say 332; the audit relies on the
actual file and records the documentation conflict.

## 3. Field-by-field compatibility matrix

| Training requirement | G10016/provider field | Semantic / units | Spatial / temporal | Quality / deterministic transform | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Each SIC lag | decoded `value.concentration` | Same documented SIC fraction, decoded 0–1 | Same grid for one date; provider returns one date only | Strict eligibility not enforced; CF decoding is direct but five-date assembly is absent | Actual file; provider `_normalized_from_dataset` | **UNKNOWN** |
| `x_m`, `y_m` | selected projected x/y provenance | Same metre units | Exact sampled EPSG:3412 grid coordinates; must remain invariant across lags | Direct for one response only | Actual x/y byte comparison; provider provenance | **COMPATIBLE** for one response |
| Seasonal pair | `observed_at` | Unitless derived pair | Daily source observation date, not retrieval time | Deterministic day-of-year sine/cosine | Provider `_observation_time` | **COMPATIBLE_WITH_DETERMINISTIC_TRANSFORM** |
| Fill/raw eligibility | finite value plus fallback fields | Fill becomes missing after CF decode | Fallback may substitute a distinct cell | No output proves original-cell eligibility for every date | Provider fallback branch | **UNKNOWN** |
| `qa_flag=0` | optional provenance QA | Same named field; unitless | One selected date/cell | Provider does not require zero and may return `None` | Provider `_selected_optional` | **UNKNOWN** |
| spatial flag `=0` | optional provenance spatial flag | Same named field; unitless | One selected date/cell | Non-zero merely marks `DEGRADED`; no model-input policy | Provider status rule | **UNKNOWN** |
| temporal flag `=0` | optional provenance temporal flag | Same named field; unitless | One selected date/cell | Non-zero merely marks `DEGRADED`; no model-input policy | Provider status rule | **UNKNOWN** |
| surface mask `=50` | no normalized field | Raw supplementary field has Ocean=50 | Native grid only | No transform/output exists | Actual file and G10016 V4 guide | **INCOMPATIBLE** |
| One same cell across all five lags | five independent provider calls | Not an individual scalar field | Fallback may vary selected x/y per call | No documented sequence invariant or rejection contract | Provider fallback behavior/tests | **INCOMPATIBLE** |

## 4. Spatial, temporal, and quality conclusion

**Spatial:** the raw products are exactly aligned for the sampled grid: CRS,
resolution, dimensions, coordinate values, and x/y hashes match. No reprojection
or invented nearest-cell calculation is needed for one returned cell. However,
a fallback can change a selected cell per date; combining such values would
violate the same-cell training contract.

**Temporal:** both data products are daily. G10016 retains roughly three months,
and the provider accepts a requested date, but returns one observation and
stores no history. A caller cannot treat retrieval time as observation time.
Building t/t−1/t−2/t−3/t−7 would require new, explicitly authorized
orchestration that rejects missing, degraded, stale-as-policy-defined,
coordinate-changing, and quality-ineligible values.

**Quality/provenance:** G10016 raw files contain equivalent ancillary fields,
but the normalized provider drops the required surface mask, does not require
QA=0, and supplies no per-window provenance. A LIVE/STALE output alone is not
evidence that it meets the training eligibility policy.

## 5. Distribution/calibration evidence

No SIC-value calibration, bias estimate, or numerical comparison was made.
The validated training corpus ends in 2024 using F17 files; the audited G10016
file is AMSR2 NRT data from 2026. These are not paired overlapping
observations. The official guide also says G10016 is preliminary and lacks the
final product's full forward-looking temporal interpolation. A calibration or
assumed interchangeability would be unsupported.

The only legitimate comparison was structural: units, scale/fill convention,
CRS, dimensions, coordinate ranges, and exact coordinate arrays. It proves
grid alignment only, not distributional equivalence or operational accuracy.

## 6. Required work before any new authorization

The audit rejects these assumptions: a LIVE/STALE point is automatically
eligible; a DEGRADED fallback equals the requested cell; retrieval time is an
observation date; and F17-trained values are calibrated to AMSR2 NRT values.

A future, separately authorized design would need deterministic, tested support
for five exact observation dates, an invariant x/y cell, strict available-flag
and surface-mask handling, missing/fallback rejection, and per-window
provenance. It would also need an explicit treatment of the sensor/product
regime difference. This audit implements none of that.

## 7. Validation

Existing provider tests: **11 passed, 1 skipped** (the opt-in live test).
Relevant Phase 5 ML/preprocessing tests: **15 passed**. Python compilation and
git diff --check passed. No raw data was tracked, no artifact changed, no
secret was added, and no commit was made.
