# KURMESH Phase 5B: Real Data Acquisition and Validation

## Scope

This phase validates a small real-data sample and the previously acquired
BYU/NIC archive. It does not preprocess a training set, train a model, calculate
model metrics, create predictions, or modify production KURMESH components.
All raw NetCDF and CSV files stayed in temporary, ignored locations; only the
metadata manifests listed below were created under `data/manifests/`.

## 1. Acquisition method and versions

### Sea ice

Six individual Antarctic daily NetCDF files were retrieved by direct HTTPS from
the official NOAA/NSIDC final CDR endpoint:

`https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily/{year}/{file}`

The product is *NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice
Concentration*, G02202 **Version 6**, final CDR. The selected dates span 46
years: 1978-10-25, 1990-01-01, 2000-01-01, 2010-01-01, 2020-01-01, and
2024-01-01. This deliberately small 2.28 MB sample validates multi-era source
consistency; it is not the eventual chronological training corpus.

### Icebergs

The existing local copy of the BYU MERS Consolidated Stats Antarctic Iceberg
Database **V3.0** archive was used; it was not downloaded again. The official
resource is `https://www.scp.byu.edu/data/iceberg/stats_database_v3.0.zip`.
The local archive remains outside the repository and has SHA-256
`aed0c7dd53dfa6d2e4a0f9b92d2419a02ff0402bb45a62d07980e11900f49fda`.

## 2. Sea-ice sample validation

| Date | File size | SHA-256 |
| --- | ---: | --- |
| 1978-10-25 | 465,225 B | `6af1029d1662d542869a0974fb9dd112dd6b4ea1eda4b79b29fa2c71efef426c` |
| 1990-01-01 | 370,047 B | `78eee62fe3ca345380ce6f25482bb3f83a7da77b22cd6c190cb683b3b5251863` |
| 2000-01-01 | 377,975 B | `ab8a06ded8a90aec97e21795df72826721cb446b22b12f54378797cad4c8b307` |
| 2010-01-01 | 363,245 B | `db6ed1c3920f82d289ac4fd27f0bb1a0f12d02672ba859e46aebbd63d36f2102` |
| 2020-01-01 | 349,465 B | `863029c5cbbf3ba58d70adf3100e6f10db1601356e04df152479e01deeb0e9a2` |
| 2024-01-01 | 355,695 B | `5e18460ead4566158894308cc87dbca8c10525cdedf84f42ca2935674c04537d` |

Actual HDF5/NetCDF decoding found the same contract in every file:

- `cdr_seaice_conc` is `uint8`, shaped `(time=1, y=332, x=316)`;
- its `standard_name` is `sea_ice_area_fraction`, its units are `1`, its raw
  valid range is 0–100, and `scale_factor=0.01` decodes valid concentrations to
  0.0–1.0;
- `_FillValue=255` occurs 21,893 times in each selected daily field. It was
  counted as missing and never converted to zero;
- `time` has `standard` calendar and `days since 1970-01-01`; each raw time
  value decodes to its filename date and the six values are strictly increasing;
- `x` is length 316 from -3,937,500 to 3,937,500 m and `y` is length 332 from
  4,337,500 to -3,937,500 m; and
- every sample has the same x/y SHA-256 hashes, shape, WKT/PROJ CRS metadata,
  and `urn:ogc:def:crs:EPSG::3412` (NSIDC South Polar Stereographic).

The actual files also include `cdr_seaice_conc_stdev`, QA, spatial- and
temporal-interpolation flags, and `surface_type_mask`. Their later eligibility
policy remains deliberately undecided; this phase only verifies their presence.
The grid is aligned across all validated dates, so one source cell can be
matched across the selected dates without resampling.

## 3. Iceberg track validation

The re-run validation over the accepted archive found 556 tracks and 398,405
CSV rows. It recomputed 394,562 consecutive 24-hour pairs, of which **308,538**
have the observed-position bit at both endpoints. It found no invalid
latitude/longitude rows, no duplicate track/date rows, and no out-of-order
adjacent valid dates.

There are 119 malformed/nonconforming date rows, which must be excluded unless
their representation is authoritatively resolved. The parsed dates range from
1976-02-01 to 2019-08-14; this conflicts with the archive landing page's
advertised coverage and remains a documented quality issue. There are 97
adjacent pairs across the longitude antimeridian in 28 tracks. Future geographic
displacement work must normalize longitude differences; it must not calculate a
naive difference across ±180°.

## 4. Reproducibility

The two machine-readable records contain resource URLs, exact hashes, schema,
grid information, and validation counts:

- `data/manifests/phase5b_sea_ice_manifest.json`
- `data/manifests/phase5b_iceberg_manifest.json`

To repeat this validation, retrieve only the six listed HTTPS NetCDF objects to
a local ignored directory, verify each SHA-256, open with an HDF5/NetCDF reader,
and compare the `cdr_seaice_conc`, x/y, time, and CRS metadata with the
manifest. For iceberg data, use the stated ZIP checksum, parse each CSV with its
filename stem as the track ID, enforce the documented date/quality/pair rules,
and count antimeridian crossings.

## 5. Data-quality issues and decision

The final CDR has sensor-regime changes (including AMSR2 from 2025), explicit
fill cells, and interpolation/QA fields. A later phase must freeze a time
interval and declare a quality policy before creating examples. The BYU/NIC
archive has malformed dates, historical-only coverage, interpolation, and
dateline crossings. These are reasons for explicit filtering and provenance,
not permission to fabricate values.

**GO for Phase 5C data preparation only.** The verified data support a
reproducible, real-data preparation phase: freeze an interval, acquire it
outside Git with hashes, and implement quality/eligibility validation. This is
not a GO for training, reporting accuracy, operational inference, routing, or
automatic action.
