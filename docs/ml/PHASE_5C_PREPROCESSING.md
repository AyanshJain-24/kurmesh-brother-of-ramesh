# KURMESH Phase 5C: Preprocessing, Features, and Leakage Prevention

## Scope and status

This phase defines and unit-tests an offline, deterministic preparation
contract. It does **not** acquire the complete corpus, create a training table,
fit a model, calculate a metric, create an artifact, or alter a KURMESH
application contract. Raw data remains outside Git. KURMESH remains
human-in-the-loop decision support; nothing here can approve or execute a
route.

Verified source facts are from [Phase 5A](PHASE_5A_SPEC.md),
[Phase 5B](PHASE_5B_VALIDATION.md), and their two machine-readable manifests.
Everything labelled **design decision** is a fixed prototype rule, not a result
from a trained model.

## 1. Verified input facts

### Sea ice: G02202 V6 final CDR

Phase 5B decoded six real Antarctic daily files. Each has
`cdr_seaice_conc` as `uint8` with shape `(1, 332, 316)`, raw valid range
0–100, `scale_factor=0.01`, and `_FillValue=255`. The decoded concentration
range is 0–1. The x/y coordinates are identical over the samples, with a 25 km
NSIDC South Polar Stereographic grid (`EPSG:3412`). The NetCDF files carry
`cdr_seaice_conc_qa_flag`, spatial/temporal interpolation flags, standard
deviation, and `surface_type_mask`.

### Icebergs: BYU/NIC V3.0 historical archive

Phase 5B validated 556 tracks and 398,405 rows. It found 394,562 consecutive
24-hour pairs and 308,538 pairs with the documented observed-position bit set
at both endpoints. It also found 119 malformed/nonconforming date rows, no
invalid coordinates, no duplicate track/date rows, and 97 antimeridian
adjacencies across 28 tracks. The source fields used here are CSV filename stem
as `track_id`, `date` (normally `YYYYDDD`), `date_gap`, `flags`, `lat`, and
`lon`. `size` is deliberately omitted: a zero value is unavailable, not a
measurement.

## 2. Frozen prototype acquisition interval and source consistency

**Design decision — sea ice interval.** The first real corpus run will request
only G02202 V6 Antarctic daily files dated **2021-01-01 through 2024-12-31**.
This is a contiguous, pre-2025 interval, avoiding an unvalidated cross-sensor
transition into the AMSR2 period. Calendar presence must be checked during
acquisition: a missing file or a grid/metadata mismatch excludes every example
requiring that date. Missing days are never synthesized or filled.

The runner must assert each file has the verified variable, scale/fill values,
shape, x/y coordinate hashes, and EPSG:3412 metadata before it contributes to
examples. It must record source URL and SHA-256 in a local/run manifest. This
phase does not claim that all 1,461 files have been retrieved.

**Design decision — iceberg interval.** The first trajectory experiment is
restricted to target dates from **1992-01-03 through 2019-08-14**. This avoids
treating the archive's anomalous 1976 date as a normal part of the experiment.
Actual eligibility remains data-dependent after the documented bad-date,
quality, and gap filters.

## 3. Deterministic sea-ice preparation

1. Decode raw `cdr_seaice_conc` as `raw * 0.01` only when raw is 0–100.
   `_FillValue=255` and every out-of-range raw value are missing, excluded, and
   counted by reason; they are never mapped to 0, mean, climatology, or a model
   input.
2. Preserve the source cell's x/y metres and integer index. Do not reproject or
   resample the native 316 × 332 grid in the prototype.
3. Retain all ancillary values in the local provenance/exclusion output.
   **Design decision — strict initial quality gate:** only records matching the
   frozen allow-lists `qa_flag=0`, spatial interpolation flag `=0`, temporal
   interpolation flag `=0`, and `surface_type_mask=50` can make examples.
   This is deliberately conservative. Phase 5C.1 verified these meanings in
   the official V6 user guide: zero is no listed QA condition and no spatial or
   temporal interpolation, while 50 is Ocean. The corpus runner must still
   reject any file whose field metadata differs from the verified contract.
4. A seven-day target window is complete only when all lag fields and the
   future label survive the same checks on the same source cell. A quality or
   availability failure excludes the entire example, with no imputation.

The implemented helper accepts already decoded per-cell records. NetCDF I/O is
intentionally not embedded in the package so it adds no dependency and makes
file provenance a responsibility of the local acquisition runner.

## 4. Sea-ice feature and target contract

For an issue date `t`, the label is the decoded `cdr_seaice_conc` at cell
`(x, y)` on `t + 7 days`. Features contain only observations at `t`, `t-1`,
`t-2`, `t-3`, and `t-7`, plus source `x_m`, `y_m`, and sine/cosine of
issue-date day-of-year. The target is stored separately and never appears in
the feature map.

This first representation is cell-level tabular data on the source grid. It is
small enough for a Ridge baseline/candidate model later; it is not a claim that
spatial context has already been modelled.

### Chronological split and purge

Splits classify **target dates**, and all cells for a target date have the same
assignment. The eligible calendar target range has 1,447 dates before file and
quality exclusions. The frozen schedule is:

| Assignment | Target dates |
| --- | --- |
| Train | 2021-01-15 – 2023-10-24 (1,013 calendar dates) |
| Purged embargo | 2023-10-25 – 2023-11-07 (14 dates) |
| Validation | 2023-11-08 – 2024-05-28 (203 calendar dates) |
| Purged embargo | 2024-05-29 – 2024-06-11 (14 dates) |
| Test | 2024-06-12 – 2024-12-31 (203 calendar dates) |

An example is rejected when *any* lag date is in a different split, embargo,
or outside the frozen interval. This intentionally loses a few boundary
windows, but prevents a training feature from being reused by validation/test
or a validation feature from being reused by test. It also prevents a missing
date from being silently bridged.

## 5. Deterministic iceberg preparation

1. Parse `date` strictly as seven-digit `YYYYDDD`; retain it only if a
   round-trip format check succeeds. Exclude malformed rows. Parse and validate
   latitude in [-90, 90] and longitude in [-180, 180); exclude invalid rows.
2. Group only by filename-derived `track_id`, sort each track by parsed date,
   and deterministically exclude repeated track/date rows. Do not join records
   across tracks.
3. Require one-day calendar differences and `date_gap == 1` for both the
   previous→issue and issue→target segments. Require the observed-position bit
   (`flags & 1`) for all three points: previous supports a past velocity
   feature, and issue/target meet the accepted target-pair rule.
4. Transform WGS84 `(lon, lat)` to EPSG:3412 through an injected,
   reproducible projector (the later runner should use the repository's
   existing `pyproj` capability with `always_xy=True`). The target is
   `future_xy - issue_xy` in metres. No future position is used in a feature.
5. Normalize every longitude difference to [-180, 180) before it is retained
   as a geographic diagnostic/feature. This handles the known 97 antimeridian
   adjacencies; a naive ±180° subtraction is forbidden.

### Iceberg feature and target contract

At issue date `t`, features are current projected x/y, the previous observed
24-hour projected displacement, normalized previous longitude difference, and
day-of-year sine/cosine. Target is the projected 24-hour displacement from `t`
to `t+1`. `track_id` groups records and records provenance; it is not a numeric
model feature. Size, future fields, and interpolated positions are excluded.

### Chronological split, grouping, and embargo

| Assignment | Target dates |
| --- | --- |
| Train | 1992-01-03 – 2011-05-02 |
| Purged embargo | 2011-05-03 – 2011-05-05 |
| Validation | 2011-05-06 – 2015-06-27 |
| Purged embargo | 2015-06-28 – 2015-06-30 |
| Test | 2015-07-01 – 2019-08-14 |

The three-day purge is longer than the two-date historical feature window and
the one-day target horizon. A single long-lived track may legitimately occur
in later time periods: it is grouped only to reconstruct its own past, not made
group-disjoint across time. The builder rejects any three-observation feature/
target window crossing an assignment boundary. This evaluates forecasting at a
future time, rather than leaking future target rows through a random split.

## 6. Baselines, candidate models, and metrics for the next phase

No model has been run. When separately authorised, the sea-ice baseline is
persistence (`sic(t)`), with a single Ridge regression candidate. The iceberg
baseline repeats the latest observed 24-hour projected displacement, with a
multi-output Ridge candidate. Train-only scaling and fitting are required;
validation chooses any fixed hyperparameter and test is used once.

The future evaluation report must calculate, from held-out real examples only:

- sea ice: MAE, RMSE, mean signed error, and per-month counts/metrics;
- icebergs: endpoint geodesic error (mean and median), x/y MAE, component bias,
  and exclusion/track counts.

No accuracy, prediction, model artifact, or metric exists at this stage.

## 7. Provenance, artifacts, and auditability

Before training, a local immutable run directory must contain:

- input resource URLs, retrieval times, SHA-256 hashes, product/version, and
  G02202 grid/variable metadata or BYU archive checksum/schema;
- exact interval, split/embargo schedule, parser version, quality allow-lists,
  exclusions by reason, and raw/eligible row counts;
- ordered feature names, units, target definition, CRS/projection settings, and
  code revision; and
- after authorised training only, train-only scaler, estimator, evaluation
  report, and checksums.

Raw NetCDF/CSV data and fitted artifacts remain ignored/outside Git. Any missing
source, undecodable field, grid mismatch, unverified flag semantics, or absent
artifact must remain explicitly `UNAVAILABLE`, `ERROR`, or `MODEL_UNAVAILABLE`
as appropriate—never a fabricated substitute.

## 8. Code and test coverage

The new dependency-free code is under `ml/preprocessing/`. Focused unit tests
cover G02202 fill/scaling/quality exclusion, chronological cross-boundary
rejection, strict malformed-date exclusion, duplicate dates, invalid date
handling, antimeridian normalization, and feature/target separation. The tests
use in-memory records only and make no claim to revalidate the full real corpus.

## 9. Phase 5D decision

**GO, conditionally, for Phase 5D offline baseline training only** after a
local acquisition runner retrieves the frozen real intervals, verifies every
file/track against this contract, and emits a complete run manifest. **NO-GO**
for production inference, routing integration, automated decisions, or any
model claim. If the strict G02202 ancillary allow-lists cannot be verified from
the official V6 documentation, Phase 5D is blocked as `UNKNOWN` until that
specific provenance issue is resolved.
