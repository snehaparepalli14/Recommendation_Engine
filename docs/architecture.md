# RecoMart architecture and design decisions

## End-to-end flow

```text
DummyJSON REST API + clickstream CSV
        |
        v
Immutable raw data lake
        |
        v
Validation and quarantine routing
        |
        v
Prepared JSON -> processed Parquet and EDA
        |
        v
DuckDB warehouse and recommendation features
        |
        v
Versioned DuckDB feature store
        |
        v
Truncated-SVD collaborative recommender
        |
        v
Top-K recommendation inference

Git + DVC version data and artefacts.
Prefect orchestrates the end-to-end workflow.
```

## Layers

1. **Source layer**: DummyJSON product, user, and cart endpoints plus clickstream CSV.
2. **Raw lake layer**: Immutable timestamped snapshots partitioned by source, entity, and ingestion date.
3. **Quality layer**: Schema, missing-value, duplicate, range, format, and relationship checks.
4. **Processed layer**: Privacy-filtered Parquet datasets, normalised fields, encoded categories, and EDA.
5. **Warehouse layer**: DuckDB dimensions, facts, and recommendation features.
6. **Feature-store layer**: Versioned feature views and metadata registry.
7. **Model layer**: Truncated-SVD collaborative filtering and popularity fallback for unseen users.
8. **Lineage layer**: Git commits, DVC metadata files, `dvc.yaml`, and `dvc.lock`.
9. **Orchestration layer**: Prefect tasks, retries, logs, dashboard monitoring, and run summaries.

## Storage and quality

Raw artefacts are saved under:

```text
data/raw/<source>/<entity>/ingestion_date=YYYY-MM-DD/
```

Each raw snapshot has a timestamped filename, source location, record count, SHA-256 checksum, and run manifest. Raw files are not edited downstream.

Validation writes accepted records to `data/prepared/` and rejected records to `data/quarantine/`. Rejected records retain source-row information and rule-level error descriptions. JSON and PDF reports provide quality evidence.

## Preparation and warehouse

Stage 3 flattens nested product dimensions and cart products, standardises types, encodes selected categorical variables, normalises selected numeric fields, and removes sensitive user attributes. Unobserved user-product pairs are treated as implicit zero-feedback rather than materialised dense rows.

Stage 4 loads Parquet outputs into `data/warehouse/recomart.db`.

- Dimensions: `dim_users`, `dim_products`
- Facts: `fact_carts`, `fact_cart_items`, `fact_events`, `fact_interactions`
- Features: `feature_user_activity`, `feature_product_popularity`, `feature_user_product`, `feature_product_cooccurrence`

The logical SQL schema is documented in `docs/warehouse_schema.sql`.

## Feature store and model

The custom feature store copies warehouse features into versioned DuckDB tables. The registry records names, keys, columns, source tables, descriptions, row counts, and version.

The recommender uses weighted implicit interactions. It applies `log1p` to interaction scores, learns a rank-12 truncated-SVD factorisation, excludes items already observed during training, and uses popularity for cold-start users.

A deterministic leave-one-product-out evaluation is performed for eligible users. The model registry and experiment report store run ID, model version, feature-store version, parameters, data summary, metrics, and artefact path.

## Data versioning and orchestration

DVC tracks raw, prepared, quarantine, processed, warehouse, feature-store, model, and report artefacts. `dvc.yaml` defines validation, preparation, feature engineering, feature-store materialisation, and model-training dependencies. `dvc.lock` records resolved fingerprints for reproducibility.

Prefect runs the operational workflow in this order:

```text
ingestion -> validation -> preparation/EDA -> feature engineering
-> feature store -> model training
```

Each task has retry behaviour. Prefect records flow status, task status, timings, and logs in its dashboard. The project also writes a JSON orchestration summary under `reports/orchestration/`.