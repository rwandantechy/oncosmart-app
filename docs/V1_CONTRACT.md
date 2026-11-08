# V1 contract

This document records behavior verified from the current repository. It is an
integration boundary for the separate EveryDoseMatters V2 proof of concept.

## Verified behavior

- The collectors are in `src/scrapers/` and cover U.S. FDA, Health Canada,
  Ghana FDA, and Nigeria NAFDAC.
- `src/main.py` runs the collectors, creates/updates SQLite, and exports a
  display CSV. Individual collector failures are logged and do not stop the
  remaining collectors.
- The repository snapshot is `src/data/recalls.db`. The verified snapshot has
  139 rows, dates from 2020-01-06 through 2026-03-12, and a latest scrape
  timestamp of 2026-03-15.
- The weekly workflow is `.github/workflows/weekly_scrape.yaml`; it runs on
  Sundays and also on pushes and pull requests. It commits the SQLite and CSV
  outputs.
- The SQLite table is `recalls` with:
  `record_id`, `source_id`, `source_org`, `source_url`, `product_name`,
  `source_country`, `manufacturer`, `distributor`, `publish_date`,
  `scraped_at`, `reason`, and `more_info`.
- `record_id`, `source_id`, `source_org`, `source_url`, and `scraped_at` are
  declared required by the SQLite schema. Other fields may be null; the
  Pydantic model currently types `product_name` as a default-null value despite
  its non-optional annotation.
- The CSV is a display export. It omits `record_id`, `source_id`, and
  `scraped_at`, so V2 imports the SQLite snapshot and uses CSV only as a
  human-readable fallback, not as the canonical source.

## V2 boundary

V2 reads a copy of the V1 SQLite file. It never writes to the V1 database,
changes the WordPress site, edits TablePress or MapGeo, or changes the legacy
collector workflow. V2 records preserve the original source URL, wording,
identifiers, source organization, source-country label, and collection time.

## Data limitations

`source_country` is preserved exactly as collected by V1. It is an associated
country value in the source record, not proof that the affected product,
incident, manufacturer, or patient was located there. V2 therefore reports it
as “country value recorded in the source alert” and keeps it separate from
`source_org`, the reporting regulatory agency. For example, a record with
`source_org` equal to NAFDAC and `source_country` equal to Ghana is not silently
reclassified as a Ghana FDA record.

The dataset contains multiple notice types, so V2 calls records “alerts” or
“notices” and does not imply that every record is a recall. Historical counts
and dates describe this imported snapshot only, not current surveillance.
V1 does not persist run-level success/failure metadata; `scraped_at` is the
latest record collection timestamp, not proof that every source completed.
