# RecoMart Data Management Pipeline

Original implementation for the **Data Management for Machine Learning - Assignment I**.

RecoMart is an e-commerce recommendation-system use case. The pipeline prepares reliable product, user, cart, and clickstream data for personalised Top-10 product recommendations.

## Business problem

RecoMart needs to improve user engagement and cross-selling by recommending products based on product attributes and observed user behaviour.

Pipeline outputs:

- Clean datasets for EDA
- Engineered recommendation features
- Versioned feature retrieval for training and inference
- Future recommendation model and inference interface

Planned model metrics:

- Precision@10
- Recall@10
- NDCG@10
- Catalog coverage

## Data sources

- **DummyJSON REST API**
  - Products: `https://dummyjson.com/products?limit=0`
  - Users: `https://dummyjson.com/users?limit=0`
  - Carts: `https://dummyjson.com/carts?limit=0`
- **Local CSV**
  - Simulated clickstream events: `data/input/clickstream.csv`

DummyJSON is cited as the demonstration data source. The project code, architecture, transformations, and documentation are original to this assignment.

## Stage 1: ingestion and raw storage

Implemented:

- REST ingestion for products, users, and carts
- CSV ingestion for clickstream events
- Configurable timeout and three retry attempts with exponential backoff
- Error handling, logs, run manifests, and checksums
- Immutable timestamped raw snapshots partitioned by source, entity, and ingestion date

```powershell
$env:PYTHONPATH = "src"
python -m recomart ingest-all
```

## Stage 2: profiling and validation

Implemented:

- Missing-value, duplicate, schema/type, range, format, and relationship checks
- Valid records routed to `data/prepared/`
- Invalid records routed to `data/quarantine/` with source-row and rule evidence
- JSON and PDF data-quality reports

```powershell
$env:PYTHONPATH = "src"
python -m recomart validate-all
```

## Stage 3: preparation and EDA

Implemented:

- Nested product dimensions and cart products flattened
- Categorical codes and min-max normalised numeric values
- Sensitive fields such as passwords, SSNs, bank, and crypto data excluded
- Sparse user-product interactions; unobserved pairs treated as implicit zero-feedback
- Parquet outputs, EDA summary, and seven plots

```powershell
$env:PYTHONPATH = "src"
python -m recomart prepare-eda
```

## Stage 4: warehouse and feature engineering

The latest Stage 3 Parquet files are loaded into a local DuckDB warehouse.

Implemented:

- User and product dimensions
- Cart, cart-item, event, and interaction facts
- User activity features
- Product popularity features
- Weighted user-product implicit-feedback scores
- Cart-based product co-occurrence features
- SQL schema and feature metadata

```powershell
$env:PYTHONPATH = "src"
python -m recomart build-features
```

## Stage 5: versioned feature store

A custom DuckDB feature store copies Stage 4 features into versioned feature views. A JSON registry records the feature names, entity keys, sources, descriptions, row counts, and version.

```powershell
$env:PYTHONPATH = "src"
python -m recomart materialize-feature-store
python -m recomart get-user-features --user-id 1 --consumer inference
```

Training and inference must request the same feature-view name and version. This prevents train-serving mismatch.

## Project structure

```text
config/                         Project settings
data/input/                     Source clickstream CSV
data/raw/                       Immutable Stage 1 snapshots
data/prepared/                  Validated Stage 2 records
data/quarantine/                Rejected records and validation evidence
data/processed/                 Stage 3 Parquet datasets
data/warehouse/                 Stage 4 DuckDB warehouse
data/feature_store/             Stage 5 feature-store database and registry
docs/                           Architecture, traceability, and SQL schema
logs/                           Pipeline execution logs
reports/data_quality/           Stage 2 JSON and PDF reports
reports/eda/                    Stage 3 EDA charts and summary
reports/features/               Stage 4 feature summaries
src/recomart/                   Application source code
tests/                          Automated tests
```

## Run all tests

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Current evidence

- 194 products, 208 users, 208 carts, and 6 clickstream events ingested and validated
- 800 cart items and 806 user-product interactions prepared
- User-item matrix sparsity: 98.0398%
- Warehouse: 208 user feature rows, 194 product feature rows, 791 user-product rows, and 1,277 co-occurrence rows
- Feature-store registry version: `v1`
- Automated tests: 16 passing

## Next stages

- Data versioning and lineage
- Recommendation model training and evaluation
- Pipeline orchestration, monitoring, and scheduling
- Final PDF report and demo video

## Stage 6: data versioning and lineage

Git and DVC version the data lifecycle without committing large data files to Git. DVC tracks the raw, prepared, quarantine, processed, warehouse, and feature-store directories; `dvc.yaml` and `dvc.lock` record the reproducible transformation graph.

```powershell
$env:PYTHONPATH = "src"
python -m dvc status
python -m dvc dag
```