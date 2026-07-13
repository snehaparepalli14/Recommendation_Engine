# Assignment requirement traceability

| Assignment task | Required evidence | Implemented location | Status |
|---|---|---|---|
| 1. Problem formulation | Problem, sources, outputs, metrics | `README.md` | Implemented |
| 2. Data collection and ingestion | REST API, CSV, retries, logging, manifests | `src/recomart/ingestion/`, `logs/` | Implemented |
| 3. Raw storage | Partitioned immutable snapshots and metadata | `src/recomart/storage.py`, `data/raw/` | Implemented |
| 4. Data profiling and validation | Automated checks, prepared/quarantine routing, PDF/JSON reports | `src/recomart/validation/`, `reports/data_quality/` | Implemented |
| 5. Preparation and EDA | Cleaning, encoding, normalisation, Parquet, plots, sparse interactions | `src/recomart/preparation/`, `data/processed/`, `reports/eda/` | Implemented |
| 6. Feature engineering | DuckDB schema, transformations, recommendation features | `src/recomart/features/`, `data/warehouse/`, `docs/warehouse_schema.sql` | Implemented |
| 7. Feature store | Versioned views, registry, training/inference retrieval | `src/recomart/feature_store/`, `data/feature_store/` | Implemented |
| 8. Versioning and lineage | DVC versions, graph, lockfile, provenance metadata | `dvc.yaml`, `dvc.lock`, `*.dvc`, `docs/data_versioning_lineage.md` | Implemented |
| 9. Model training and evaluation | Collaborative SVD model, metrics, tracked metadata | `src/recomart/models/`, `models/`, `reports/model_evaluation/`, `reports/experiments/` | Implemented |
| 10. Pipeline orchestration | Prefect flow, retries, monitoring, logs, execution summary | `src/recomart/orchestration/`, `reports/orchestration/` | Implemented |

## Key acceptance evidence

### Data quality

- Products, users, carts, and events are validated for missing values, duplicates, schemas, types, ranges, formats, and relationships.
- Valid records are routed to prepared storage; invalid records include rule-level evidence in quarantine.
- JSON and PDF quality reports are generated.

### Preparation and features

- Nested product and cart structures are flattened.
- Categorical values are encoded and selected numeric variables are normalised.
- Sensitive user fields are excluded.
- Processed data contains 806 interactions with 98.0398% user-item sparsity.
- Warehouse features include user activity, product popularity, weighted user-product scores, and co-occurrence counts.

### Feature store and lineage

- Feature-store version `v1` contains four registered feature views.
- Training and inference use the same explicit feature version.
- DVC tracks data and generated model/report artefacts without storing large data files in Git.
- DVC pipeline status is up to date.

### Model training and evaluation

- A rank-12 truncated-SVD collaborative filtering model is trained from weighted implicit interactions.
- Evaluation uses a deterministic one-item-per-user holdout.
- Results: Precision@10 = 0.0082, Recall@10 = 0.0817, NDCG@10 = 0.0367, catalogue coverage = 0.6443.
- JSON experiment tracking stores run IDs, parameters, data summary, metrics, feature-store version, and model path.
- Inference returns personalised Top-10 products and uses popularity fallback for unseen users.

### Orchestration

- Prefect runs ingestion, validation, preparation/EDA, feature engineering, feature-store materialisation, and model training in sequence.
- Tasks have retry settings and failures are recorded by Prefect and the local orchestration summary.
- Dashboard evidence shows successful flow and task runs with no failed or crashed runs.
- The automated suite contains 19 passing tests.