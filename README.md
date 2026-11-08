# Oncology Medicine Report Dashboard

CLI scrapers for oncology medicine recalls from FDA Ghana, FDA USA, NAFDAC, and Health Canada. Results are stored in SQLite and exported to CSV.

## Run locally

Running the API and frontend together is documented in the workspace README one
directory up, which owns every Make target; the Makefile here only forwards to
it, so `make api` works from either directory. The rest of this file covers the
scrapers, which are specific to this repository.

Install the locked dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run all scrapers using the default start date (`2020-01-01`):

```bash
PYTHONPATH=.:src uv run python src/main.py
```

To use a different start date:

```bash
PYTHONPATH=.:src uv run python src/main.py --start-date 2024-01-01
```

To refresh the oncology drug list from the NCI instead:

```bash
PYTHONPATH=.:src uv run python src/main.py --update-drug-database
```

The scraper writes:

- `src/data/recalls.db` — SQLite database
- `src/data/recalls.csv` — exported recall report
- `src/data/nci_oncology_drugs.json` — updated by `--update-drug-database`

Set `LOG_LEVEL` to change logging verbosity, for example:

```bash
LOG_LEVEL=DEBUG PYTHONPATH=.:src uv run python src/main.py
```

## Run tests

```bash
uv run pytest
```

Configuration lives in `env.example`; copy it to `.env`, which is ignored.
Every operational value the API reads comes from the environment, so no key,
path, limit, or label is hardcoded.
