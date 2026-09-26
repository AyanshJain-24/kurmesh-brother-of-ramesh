# KURMESH Phase 5C.1: Ancillary Flags and Full-Corpus Pre-Training Validation

## Scope and status

This phase verifies G02202 V6 ancillary-field semantics and runs an offline
pre-training validation of the frozen Antarctic 2021–2024 daily corpus. It does
not train a model, calculate model metrics, write a training dataset, create a
model artifact, or modify a production component. Raw NetCDF and CSV data stay
in local temporary directories outside Git.

**Status: COMPLETE / GO for the narrowly scoped Phase 5D offline baseline
training phase.** Both required pre-training data gates passed. This is not a
GO for operational inference, routing, automatic decision-making, metrics, or
any production integration.

## 1. Official G02202 V6 ancillary-field verification

The authoritative reference is NSIDC's *USER GUIDE: NOAA/NSIDC Climate Data
Record of Passive Microwave Sea Ice Concentration, Version 6*, Tables 3–5 and
the variable descriptions (pp. 7–14), published with G02202 V6:

<https://nsidc.org/sites/default/files/documents/user-guide/g02202-v006-userguide.pdf>

| Variable | Official documented meaning / encoding | Phase 5C selected value | Decision |
| --- | --- | --- | --- |
| `cdr_seaice_conc_qa_flag` | Unitless unsigned-byte condition bit sum. Southern files have valid range 0–127. Table 4 defines bits 1, 2, 4, 8, 16, 32, and 64 for weather filters, land spillover, no input data, invalid ice mask, spatial interpolation, and temporal interpolation. The guide states a cell meeting multiple conditions stores their sum. | `0` | **ACCEPTED.** Zero is the absence of every listed condition bit; it is not merely presumed “best.” |
| `cdr_seaice_conc_interp_spatial_flag` | Unitless unsigned-byte bit sum, range 0–63. Table 3 defines 1, 2, 4, 8, 16, and 32 for interpolated brightness-temperature channels/pole-hole handling. The guide explicitly states a cell not spatially interpolated is set to zero. | `0` | **ACCEPTED.** Explicitly means no spatial interpolation. |
| `cdr_seaice_conc_interp_temporal_flag` | Unitless unsigned byte, range 0–55. It records source-day offsets used for temporal concentration interpolation; examples are 24 (two prior/four future), 30 (three prior), and 1 (one future). The guide explicitly states 0 means no temporal interpolation. | `0` | **ACCEPTED.** Explicitly means no temporal interpolation, preventing future-source contamination in the historical forecasting examples. |
| `surface_type_mask` | Unitless unsigned byte, range 50–250. Table 5 maps 50 Ocean, 75 Lakes, 100 Pole hole, 200 Coast, and 250 Land. | `50` | **ACCEPTED.** Explicitly selects ocean source cells. |

The Phase 5C strict eligibility policy is therefore unchanged:
`qa_flag == 0`, `spatial_interpolation_flag == 0`,
`temporal_interpolation_flag == 0`, and `surface_type_mask == 50`, in addition
to the existing concentration raw-range/fill rules. The code and Phase 5C
documentation now record that this is official evidence, not an unresolved
allow-list assumption.

## 2. Sea-ice full-corpus acquisition and validation procedure

The ML-only validator is
[`ml/validation/phase5c1_sea_ice.py`](../../ml/validation/phase5c1_sea_ice.py).
It requests only the frozen G02202 V6 Southern daily interval
2021-01-01–2024-12-31 from:

`https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily/{year}/sic_pss25_{date}_F17_v06r00.nc`

Each successful object is retained only in a system temporary folder and is
validated for HTTP success, SHA-256, one daily timestamp matching filename
date, required fields, `(332, 316)` concentration/ancillary shape, G02202
`_FillValue=255`, raw range 0–100, `scale_factor=0.01`, unit `1`, x/y hashes,
and CRS metadata containing EPSG:3412. It records per-file URL/hash/metadata,
flag distributions, and grid consistency in a local JSON manifest outside Git.
Any failure is listed as a missing or malformed date; there is no repair,
substitution, or zero fill.

### Completed acquisition result

All **1,461 expected files** validated successfully. There were **0 missing
files**, **0 corrupt/malformed files**, **0 duplicate dates**, and **0 grid
inconsistencies**. Every file had the expected field set, time/date, decoding
metadata, and EPSG:3412 marker. The common native grid is `(332, 316)` with
x/y SHA-256 values
`c82b5ad53e3404a93a13556ee2f9def0c619fe5d3fd3a797cd05794f7909d535` and
`14063bef7b727ed29f86b7ee723793d5ad4fa8c40c7ce7d7a95e236d2be6e3e2`.

The complete per-file source URL, SHA-256, file size, time value, decoding
metadata, and ancillary distributions are recorded in the local-only manifest
`%TEMP%/kurmesh-phase5c1/phase5c1_sea_ice_local_manifest.json`; it is not
placed in Git because it names the local raw-data run.

Across 153,276,432 source cells, 121,290,759 had ocean mask value 50 and
31,985,673 were fill/missing SIC cells. The raw SIC range had **0** values
outside the documented 0–100 range. The independently counted policy fields
were: 95,276,735 non-zero QA cells, 216,244 spatially interpolated cells,
905,377 temporally interpolated cells (excluding fill code 255), and
31,985,673 non-ocean-mask cells. Criteria overlap, so these figures must not
be added together. The strict joint policy retained **26,014,024 cells**
(16.972% of all source cells).

## 3. Preprocessing dry-run rules

The validator uses the existing `SeaIceCellRecord` eligibility ordering:
fill value, out-of-range concentration, QA, spatial interpolation, temporal
interpolation, then surface mask. It counts the first rejecting reason per
candidate cell/window. A candidate requires observed/eligible values at issue
lags 0, 1, 2, 3, and 7 days plus the seven-day future label. It rejects an
entire cell/date candidate when a required date is missing or crosses a
train/validation/test/embargo boundary. It creates no persisted feature table.

Features per example are nine scalars: five SIC lags, source x/y, and
day-of-year sine/cosine. Target is one separately stored scalar SIC fraction.

### Completed real-data dry run

The complete corpus produced **1,377** calendar target dates with complete
file windows (2021-01-29–2024-12-31), of which **1,349** had at least one valid
example. It considered 144,463,824 candidate cell/windows and constructed
**21,529,379 valid seven-day same-cell examples** (14.903%). The split counts
are 16,086,664 train, 1,651,690 validation, and 3,791,025 test examples.

The dry run rejected 30,146,661 candidate windows first for a fill value and
92,787,784 first for a non-zero QA flag; none first failed the later spatial,
temporal, or surface-mask checks because the QA flag already records those
conditions for the affected cells. Every candidate was assigned by target date
and rejected if any feature timestamp fell in a different split or embargo, so
no target crosses a split boundary.

## 4. Iceberg real-archive preprocessing dry run

The existing local BYU/NIC V3 archive was reused without a download. The
ML-only runner processed all **556 tracks** and **398,405 rows**. It excluded
**119 malformed date rows**, found **0 invalid-coordinate rows** and **0
duplicate track/date rows**, and found the previously established **97**
antimeridian-adjacent segments.

With the Phase 5C strict parser, observed-position requirement on previous,
issue, and future points, and both required one-day `date_gap`/calendar
segments, it constructed **298,581** unique valid examples:

| Split | Examples |
| --- | ---: |
| Train | 189,892 |
| Validation | 49,245 |
| Test | 59,444 |

Each example has seven past-only features and a separate two-component future
displacement target. No duplicate examples were produced. All 97 antimeridian
adjacencies passed normalized-longitude validation; no feature retained an
unnormalized longitude difference outside [-180, 180).

The final controlled run used the repository-declared `pyproj==3.8.0` and
`Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True)`. It had
**0 projection failures** and all 298,581 projected displacement magnitudes
were finite. Magnitudes were 0–868,851.17 m, with mean 3,624.01 m and median
0 m; these are descriptive source-data statistics, not model metrics.

Representative checks included an ordinary pair and both directions across the
antimeridian. The eastward `b10b` pair (1997-07-12→13) normalized
174.544°→−179.919° to +5.537°, yielding dx/dy
−220,731.82/−16,849.54 m and a finite 221,373.99 m magnitude. The westward
`b10b` pair (1997-06-03→04) normalized −179.952°→179.770° to −0.278°, yielding
10,501.85/−3,885.51 m and a finite 11,197.59 m magnitude. Future endpoint
coordinates remain labels only; the six input features are past-only.

## 5. Remaining limitations and Phase 5D decision

- The strict sea-ice quality policy excludes most source cells. This is an
  intentional defensible prototype filter, not a completeness claim.
- BYU/NIC data remain historical and include malformed dates, interpolation,
  zero-displacement repeats, and occasional very large observed displacements;
  these must be retained as provenance/exclusion considerations in Phase 5D.
- Neither source is an operational model input or a route-approval mechanism.

**Phase 5D decision: GO for offline, real-data baseline training only.** The
future phase must use the frozen manifests/policies, fit transforms on training
data only, and produce real held-out results. Production inference, routing
integration, automatic decisions, and accuracy claims remain out of scope.
