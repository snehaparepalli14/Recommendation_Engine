# RecoMart Data Management Pipeline

Original implementation for the Data Management for Machine Learning assignment.

RecoMart is an e-commerce recommendation use case. The project turns product, user, cart, and clickstream data into a validated, versioned, feature-managed pipeline that trains and serves personalised Top-10 product recommendations.

## Business problem

RecoMart wants to improve customer engagement and cross-selling through product recommendations based on user behaviour and product interactions.

Expected outputs:

- Clean datasets and EDA artefacts
- Warehouse features for collaborative recommendation
- Versioned feature retrieval for training and inference
- Trained recommender model and Top-K inference interface
- Reproducible, monitored end-to-end execution

Evaluation metrics are Precision@10, Recall@10, NDCG@10, and catalogue coverage.

## Data sources

- DummyJSON REST API: products, users, and carts
- Local CSV: simulated clickstream events

The project architecture, processing logic, source code, model, and documentation were created specifically for this assignment.

## Implemented pipeline

| Assignment task | Implementation |
|---|---|
| 1. Problem formulation | RecoMart recommendation objective, sources, outputs, and metrics |
| 2. Ingestion | DummyJSON REST API and clickstream CSV ingestion with retries, logs, and manifests |
| 3. Raw storage | Immutable timestamped snapshots with SHA-256 checksums |
| 4. Validation | Profiling, validation, prepared/quarantine routing, JSON/PDF reports |
| 5. Preparation and EDA | Cleaning, encoding, normalisation, Parquet outputs, seven plots |
| 6. Feature engineering | DuckDB warehouse, dimensions, facts, activity, popularity, and co-occurrence features |
| 7. Feature store | Versioned DuckDB feature views with a JSON registry |
| 8. Versioning and lineage | Git, DVC data versions, reproducible stages, and lockfile |
| 9. Model training | Truncated-SVD collaborative filtering, Top-K evaluation, and JSON experiment tracking |
| 10. Orchestration | Prefect flow with ordered tasks, retries, monitoring, logs, and execution summaries |

## prerequisite
```
pip install -r requirements.txt   
```

## Commands

```powershell
$env:PYTHONPATH = "src"

python -m recomart ingest-all
python -m recomart validate-all
python -m recomart prepare-eda
python -m recomart build-features
python -m recomart materialize-feature-store

python -m recomart get-user-features --user-id 1 --consumer inference
python -m recomart train-model --rank 12 --top-k 10
python -m recomart recommend --user-id 1 --limit 10

python -m dvc status
python -m unittest discover -s tests -v
```

## Orchestration

Start the local Prefect server in one terminal:

```powershell
prefect server start
```

In a second activated project terminal:

```powershell
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
python -m recomart orchestrate-all --skip-ingestion
```

Open `http://127.0.0.1:4200` to view flow runs, task states, logs, durations, and retries.

## Current evidence

- 194 products, 208 users, 208 carts, and 6 clickstream events validated
- 800 cart items and 806 user-product interactions prepared
- User-item matrix sparsity: 98.0398%
- Warehouse: 208 user rows, 194 product rows, 791 user-product rows, and 1,277 co-occurrence rows
- Feature-store version: `v1`
- SVD evaluation: Precision@10 = 0.0082, Recall@10 = 0.0817, NDCG@10 = 0.0367, catalogue coverage = 0.6443
- Prefect monitoring: successful flow and task runs with no failed or crashed runs
- Automated tests: 19 passing
- DVC: data and pipelines up to date

## Project structure

```text
config/                     Project configuration
data/input/                 Clickstream source CSV
data/raw/                   Immutable raw snapshots
data/prepared/              Validated records
data/quarantine/            Invalid records and error evidence
data/processed/             Cleaned Parquet datasets
data/warehouse/             DuckDB warehouse
data/feature_store/         Versioned feature views and registry
models/                     Trained SVD model and registry
reports/                    Quality, EDA, feature, model, experiment, and orchestration evidence
docs/                       Architecture, lineage, traceability, and SQL schema
src/recomart/               Modular pipeline source code
tests/                      Automated tests
dvc.yaml / dvc.lock         Reproducible data lineage
```

## Limitations and future scope

The current dataset is sparse and mostly contains simulated cart interactions. More real clickstream events, purchases, timestamps, and explicit ratings would improve the recommendation model. Future work can compare SVD against content-based and hybrid recommenders, tune hyperparameters, schedule Prefect deployments, and publish a production inference API.
