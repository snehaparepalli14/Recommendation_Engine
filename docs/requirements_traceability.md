# Assignment requirement traceability

| Assignment task | Required evidence | Implemented location | Status |
|---|---|---|---|
| 1. Problem formulation | Business problem, sources, outputs, and metrics | `README.md` | Implemented |
| 2. Data collection and ingestion | REST API + CSV, retry, error handling, logs | `src/recomart/ingestion/`, `src/recomart/pipeline.py`, `logs/` | Implemented |
| 3. Raw data storage | Timestamped partitioned snapshots and metadata | `src/recomart/storage.py`, `data/raw/`, `docs/architecture.md` | Implemented |
| 4. Data profiling and validation | Automated validation, prepared/quarantine outputs, JSON/PDF reports | `src/recomart/validation/`, `data/prepared/`, `data/quarantine/`, `reports/data_quality/` | Implemented |
| 5. Data preparation and EDA | Cleaning, categorical encoding, normalisation, Parquet, plots, sparse interactions | `src/recomart/preparation/`, `data/processed/`, `reports/eda/` | Implemented |
| 6. Feature engineering and transformation | SQL schema, DuckDB warehouse, transformations, feature logic | `src/recomart/features/`, `data/warehouse/`, `docs/warehouse_schema.sql`, `reports/features/` | Implemented |
| 7. Feature store | Versioned feature views, metadata registry, training/inference retrieval | `src/recomart/feature_store/`, `data/feature_store/` | Implemented |
| 8. Data versioning and lineage | DVC or equivalent lineage implementation | Future stage | Planned |
| 9. Model training and evaluation | Recommender, metrics, and experiment tracking | Future stage | Planned |
| 10. Pipeline orchestration | Automated workflow, monitoring, and failure evidence | Future stage | Planned |
| Submission | PDF report, ZIP, and demo video | Future stage | Planned |

## Stage 1 acceptance evidence

- Products, users, and carts are collected through REST APIs.
- Clickstream events are collected from a CSV file.
- API requests use timeout, retry, and exponential backoff.
- Raw files are partitioned by source, entity, and ingestion date.
- Raw snapshots have timestamps, record counts, and SHA-256 checksums.
- Logs and pipeline manifests provide audit evidence.

## Stage 2 acceptance evidence

- Products, users, carts, and events are validated automatically.
- Missing values, duplicates, schemas, types, ranges, formats, and references are checked.
- Valid records are written to prepared storage.
- Invalid records are written to quarantine with explicit validation errors.
- JSON and PDF quality reports are generated.
- Latest real validation result: 194 products, 208 users, 208 carts, and 6 events valid.

## Stage 3 acceptance evidence

- Only validated Stage 2 records are used.
- Nested product and cart structures are flattened.
- Categorical codes and min-max-normalised numerical values are created.
- Unobserved user-product pairs are treated as implicit zero-feedback.
- Sensitive user fields are excluded.
- Parquet datasets, seven EDA charts, and a JSON summary are generated.
- Latest result: 800 cart items, 806 interactions, and 98.0398% sparsity.

## Stage 4 acceptance evidence

- Processed Parquet data is loaded into a DuckDB warehouse.
- Dimension, fact, and feature tables are created reproducibly.
- User activity, product popularity, user-product, and co-occurrence features are generated.
- SQL logical schema is stored in `docs/warehouse_schema.sql`.
- Feature summaries and metadata are generated.
- Latest warehouse result: 208 user rows, 194 product rows, 791 user-product rows, and 1,277 co-occurrence rows.

## Stage 5 acceptance evidence

- Feature-store database is separate from the DuckDB warehouse.
- Version `v1` stores four registered feature views.
- JSON registry records source, keys, feature columns, description, row count, and version.
- Training and inference retrieval use the same explicit version.
- Automated tests verify matching training and inference retrieval.
- The complete automated suite has 16 passing tests.

## Stage 6 acceptance evidence

- DVC tracks raw, prepared, quarantine, processed, warehouse, and feature-store data artefacts through content-addressed metadata files.
- `dvc.yaml` defines validation, preparation/EDA, feature engineering, and feature-store materialisation stages.
- `dvc.lock` records resolved dependency fingerprints and commands for reproducibility.
- `dvc dag` provides a visible raw-to-feature-store lineage graph.
- Raw manifests, quality reports, summaries, and the feature registry retain source, timestamp, and transformation context.