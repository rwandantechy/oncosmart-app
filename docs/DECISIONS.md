# V2 decisions

## Historical demo status

The initial V2 dataset is a local, historical snapshot. The API labels it
“Historical snapshot — not current surveillance” and exposes its import,
publication, and last-recorded-collection metadata. It does not apply an
arbitrary age threshold to call a dataset fresh. The availability state is
derived from validation/import metadata; a historical snapshot is never
described as live monitoring.

## Read-only V1 import

The importer opens the V1 SQLite source in read-only mode, validates schema,
URLs, identifiers, and record counts, then stages and transactionally replaces
the V2 snapshot only after validation and staged row counts succeed. Failed
validation is recorded in `import_runs` and cannot replace the last trusted
snapshot. The source file is never modified.

## AI

The first explanation provider is optional local Ollama; Gemini is not
integrated. Search, detail, and analytics work without AI. When the feature
flag is off, the API returns a deterministic template based only on imported
fields and labels it as an alert summary. When enabled, the server sends
selected evidence to Ollama, validates structured output, and falls back to
the deterministic summary when Ollama is unavailable or unsupported. Any
future provider must remain server-side, feature-flagged, validated,
rate-limited, and clearly separated from regulator wording.

The currently available local models were `qwen3:0.6b` and `qwen3:4b`;
`qwen3:8b` was not installed. The model is configured with `OLLAMA_MODEL`.

## Research workspace

The owner preview uses the same validated V2 snapshot as the public search.
Its research brief exposes keyword-based indicators derived from the stored
`reason` field, publication-year counts, top product names, and a CSV export
that preserves stable identifiers and source provenance. These indicators are
descriptive only; they are not clinical classifications, incidence,
prevalence, or risk estimates. The owner preview remains unauthenticated and
must not be deployed as an administrative system until authentication and
authorization are implemented.
