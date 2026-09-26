# KURMESH Phase 5A: Verified ML Experiment Specification

## Scope

This document records source verification and a proposed minimal experiment
only. It does not download a corpus into this repository, prepare training rows,
train a model, compute metrics, register artifacts, run inference, or alter any
KURMESH application contract. KURMESH remains human-in-the-loop decision
support: neither proposed model can approve, execute, or create a route.

Verification was performed on 2026-09-24 from `feature/ml-phase5` at baseline
`06b641c`. Raw downloads were temporary and are not stored in Git.

## 1. Verified data-source evidence

### Accepted sea-ice source: NOAA/NSIDC G02202 Version 6

**Dataset/product.** The accepted source is the *NOAA/NSIDC Climate Data Record
of Passive Microwave Sea Ice Concentration*, **G02202 Version 6** (final CDR),
published by the National Snow and Ice Data Center for the NOAA/NCEI Climate
Data Record Program. The official [catalog](https://nsidc.org/data/g02202/versions/6)
identifies a daily and monthly, 25 km record from 1978-10-25 to present for both
polar regions, and documents the Antarctic grid as NSIDC South Polar
Stereographic, EPSG:3412.

**Actual access.** The official HTTPS source is
`https://noaadata.apps.nsidc.org/NOAA/G02202_V6/`. Live directory requests
returned its `south/` hierarchy and individual Antarctic daily files. The 1978
listing contains `sic_pss25_19781025_n07_v06r00.nc`, while 2024 and 2025
listings contain daily files, demonstrating multi-date, multi-year historical
availability rather than merely a catalog description. The published
[access instructions](https://nsidc.org/data/user-resources/help-center/how-access-and-download-noaansidc-data)
state that NOAA/NSIDC data can be downloaded directly through HTTPS.

A real historical sample was retrieved from:

```text
https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily/1978/sic_pss25_19781025_n07_v06r00.nc
```

It is an HDF5-backed NetCDF file, 465,225 bytes, with SHA-256
`6af1029d1662d542869a0974fb9dd112dd6b4ea1eda4b79b29fa2c71efef426c`.
Its embedded metadata strings include `cdr_seaice_conc`, standard deviation,
QA, spatial- and temporal-interpolation fields, `surface_type_mask`,
`scale_factor`, `_FillValue`, and `EPSG:3412`. This is direct evidence of a
real, machine-readable historical object; the temporary sample is not part of
the repository.

**Data contract.** The official [Version 6 user guide](https://nsidc.org/sites/default/files/documents/user-guide/g02202-v006-userguide.pdf)
documents these Antarctic daily properties:

| Property | Verified specification |
| --- | --- |
| Target variable | `cdr_seaice_conc`: fraction of ocean area covered by sea ice |
| Temporal resolution | Daily; monthly products also exist |
| Spatial grid | 316 x 332 (x/y) Antarctic source cells; 25 km grid |
| Coordinates / CRS | `x`, `y` in metres; NSIDC South Polar Stereographic EPSG:3412 |
| Stored range and decoding | unsigned byte 0–100 with `scale_factor=0.01`, conventionally decoded to fraction 0–1 |
| Missing value | 255 |
| Quality context | `cdr_seaice_conc_qa_flag`, `cdr_seaice_conc_interp_spatial_flag`, `cdr_seaice_conc_interp_temporal_flag`, `cdr_seaice_conc_stdev`, and `surface_type_mask` are documented |
| Format | NetCDF/HDF5, individual daily files; the source also provides aggregated products |

The source grid contains 104,912 cells per daily field. Individual verified
directory listings show roughly 0.30–0.47 MB per daily file. A compact prototype
acquisition of four historical calendar years, 2021–2024, is approximately
0.44–0.69 GB before local decompression/derived working files (1,461 daily
files at the observed 0.30–0.47 MB range). It must be downloaded to a local
ignored workspace or external data location, not Git. The exact URLs, retrieval
time, and SHA-256 for every later acquired file must be recorded in a dataset
manifest.

**Why accepted.** The source has an official publisher, actual reproducible
file access, a retrieved historical sample, daily observations over decades, a
documented concentration field, source coordinates/CRS, and a sufficient
contiguous multi-year interval for chronological train/validation/test periods.
Known missing daily periods and quality/interpolation flags must be handled by
the later data-preparation policy, not fabricated away.

### Accepted iceberg source: BYU/NIC Antarctic Iceberg Tracking Database

The previously verified **BYU/NIC Antarctic Iceberg Tracking Database
statistical archive V3.0** remains accepted for an offline historical trajectory
experiment. Its established real-data evidence is retained without a new
download:

- 556 CSV tracks;
- 398,405 rows; and
- 308,538 consecutive 24-hour pairs whose endpoints have the documented
  observed-position bit.

The required input fields are the CSV filename stem as `track_id`, `date`
(documented normally as `YYYYDDD`), `lat`, `lon`, and `flags`. The least
significant `flags` bit is required to exclude pairs whose endpoints are wholly
interpolated. `date_gap` is required to verify consecutive daily observations.
`size` is genuinely present as a scatterometer-based estimate, but it is not
required for the minimum model; if used later, zero means no estimate and is
not a measured size. The documented archive fields also include `disp`, `mask`,
and `vel_angle`.

This source supports historical trajectory reconstruction and 24-hour target
construction, subject to an explicit later exclusion policy for malformed dates,
gaps, interpolation, and documented position-quality limitations. It is not a
current operational iceberg-position feed.

## 2. Rejected data sources and reasons

| Source | Decision | Reason |
| --- | --- | --- |
| NOAA/NSIDC G02202 Version 4 | Rejected | Officially retired; its historical endpoint previously returned HTTP 404. It must not be used as training data. |
| NOAA/NSIDC G10016 Version 4 | Rejected as the historical training corpus | It is a reachable daily NetCDF operational/NRT source, but its official catalog says it supplies only the most recent three months. That window does not support a credible multi-period chronological historical experiment. It may be examined in a later, separately authorised inference-compatibility task, not used here as the historical corpus. |

## 3. Minimal executable experiment contract

Nothing in this section has been run. It is limited to what the verified data
availability supports.

### Sea ice

| Item | Proposed contract |
| --- | --- |
| Prediction target | Decoded `cdr_seaice_conc` fraction at the same EPSG:3412 source cell, seven days after issue date |
| Supported forecast horizon | 7 days, because G02202 V6 provides daily fields |
| Spatial representation | Native fixed 316 x 332 EPSG:3412 25 km grid; retain source x/y coordinates and do not resample in the first prototype |
| Features | Valid values at t, t-1, t-2, t-3, and t-7; grid x/y; day-of-year sine/cosine; recorded quality/interpolation state only for filtering/provenance |
| Baseline | Persistence: predict `sic(t)` at t+7 |
| Simple ML model | One Ridge regression per horizon over the stated lag, spatial, and seasonal features |
| Split | Chronological target-date split: earliest 70% train, next 15% validation, last 15% test; keep all cells from a target date together and purge a seven-day embargo at boundaries |
| Metrics | Held-out MAE, RMSE, and mean signed error, overall and by month; report valid/excluded rows and reasons |

Exclude fill/mask/out-of-range values and labels marked by the later declared
quality policy. Do not treat interpolation flags as fresh measurements, fill
missing values with zero/climatology, or report any metric before a real split
is evaluated.

### Icebergs

| Item | Proposed contract |
| --- | --- |
| Prediction target | Direct 24-hour displacement `(delta_x_m, delta_y_m)` between observed positions after transforming WGS84 latitude/longitude to EPSG:3412 |
| Supported forecast horizon | 24 hours, established by 308,538 observed-endpoint consecutive pairs |
| Features | Latest and preceding observed positions/displacements, day-of-year sine/cosine; `track_id` used only for grouping and split checks; size omitted from the minimum model |
| Baseline | Constant velocity: repeat the latest 24-hour observed displacement |
| Simple ML model | Multi-output Ridge regression for easting and northing displacement |
| Split | Chronological target-date split, 70%/15%/15%, with all observations for a target date assigned together and a 72-hour embargo around boundaries; no random row shuffle |
| Metrics | Held-out endpoint geodesic error (median and mean), easting/northing MAE, and component bias; report pairs, tracks, and exclusions |

Only a direct, gap-free, observed-position pair qualifies for the target.
Interpolation, gap repair, trajectory fabrication, and a model-derived
confidence score are outside this prototype.

## 4. Artifact requirements for a later authorised implementation

No artifact exists yet. Before any training result can be used or described,
the later phase must create immutable, checksummed artifacts outside Git as
appropriate:

- dataset manifest: source/version, file URLs, retrieval timestamps, checksums,
  coverage, variable schema, decoding, CRS, and exclusions;
- feature specification: ordered feature names, units, lag rules, quality policy,
  transforms, and target definition;
- split manifest: cut dates, embargo dates, counts, and deterministic selection
  settings;
- serialized estimator and dependency/version metadata; and
- evaluation report generated from the held-out real data, including the same
  baseline and exclusion counts.

Any unavailable source, artifact, compatibility check, or required input must
remain `MODEL_UNAVAILABLE`; it must never be replaced with a fabricated output.

## 5. Known limitations and remaining uncertainty

- G02202 V6 changes input sensor regime to AMSR2 from 2025. A first experiment
  should freeze a pre-2025 training/evaluation interval or explicitly document
  the regime boundary; it must not assume cross-sensor equivalence.
- G02202 V6 includes quality control and gap-filling/interpolation products.
  The exact inclusion/exclusion policy is deliberately not designed or executed
  here.
- The G02202 V6 final CDR and G10016 V4 NRT operational product have not been
  decoded and compared cell-by-cell in this task. Operational handoff
  compatibility is therefore **UNKNOWN**.
- BYU/NIC trajectories are historical and have documented interpolation, gaps,
  position jumps, and noisy size estimates; the data are not evidence of all
  iceberg presence or present-day operational coverage.
- No model, artifact, prediction, training metric, accuracy claim, or inference
  integration has been completed.
