# Data versioning and lineage

## Purpose

RecoMart uses Git and DVC to reproduce the data state used by the recommendation pipeline without committing large raw, processed, warehouse, or feature-store files to Git.

## Versioned data artefacts

| DVC metadata file | Versioned data |
|---|---|
| `data/raw.dvc` | Immutable API and clickstream snapshots, manifests, checksums |
| `data/prepared.dvc` | Records that passed Stage 2 validation |
| `data/quarantine.dvc` | Rejected records and validation evidence |
| `data/processed.dvc` | Stage 3 Parquet datasets |
| `data/warehouse.dvc` | Stage 4 DuckDB warehouse and feature reports |
| `data/feature_store.dvc` | Stage 5 feature-store database and versioned registry |

The DVC metadata files contain content hashes. Git versions those files, while DVC manages the actual data files through its local cache.

## Reproducible transformation graph

`dvc.yaml` records four reproducible transformations:

```text
raw -> validate -> prepared -> prepare_eda -> processed
    -> build_features -> warehouse -> materialize_feature_store -> feature_store
```

Quarantine data is produced by validation and versioned independently because it is evidence of data-quality failures rather than an input to later transformations.

## Metadata and audit evidence

Data provenance is layered rather than stored in one file:

- Stage 1 manifests record source URL or local path, run ID, ingestion timestamp, checksum, and record count.
- Stage 2 reports record validation rules, routing decisions, and source artefacts.
- Stage 3 and Stage 4 summaries record source files, generated outputs, and transformation results.
- Stage 5 registry records feature-view version, keys, columns, source, and row count.
- `dvc.lock` records the exact dependencies and commands used for each reproducible stage.

## Normal workflow

```powershell
python -m recomart ingest-all
python -m dvc add data/raw
python -m dvc repro
python -m dvc add data/prepared data/quarantine data/processed data/warehouse data/feature_store
python -m dvc status
python -m dvc dag
```

Commit code and metadata, not large data directories:

```powershell
git add .dvc .dvcignore dvc.yaml dvc.lock data/*.dvc data/.gitignore
git add src config docs requirements.txt tests README.md
git commit -m "Add reproducible data lineage"
```

`dvc status` must report that data and pipelines are up to date before submission. `dvc dag` is suitable evidence for the demonstration video and final report.