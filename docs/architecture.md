# RecoMart architecture and design decisions

## Pipeline layers

1. **Source layer**: DummyJSON REST endpoints and local clickstream CSV.
2. **Raw lake layer**: Immutable JSON and CSV snapshots partitioned by source, entity, and date.
3. **Quality layer**: Profiling, validation, prepared routing, quarantine routing, and quality reports.
4. **Processed layer**: Cleaned, privacy-filtered Parquet datasets and EDA artefacts.
5. **Warehouse layer**: DuckDB dimensions, facts, and engineered recommendation features.
6. **Feature-store layer**: Versioned feature views and metadata registry for training and inference.
7. **Model layer**: Planned content-based, collaborative, and hybrid recommenders.
8. **Orchestration layer**: Planned scheduling, monitoring, and failure handling.

## Overall flow

```text
DummyJSON REST API + Clickstream CSV
-> Immutable raw lake snapshots
-> Validation and quarantine routing
-> Prepared valid datasets
-> Processed Parquet datasets and EDA
-> DuckDB warehouse and engineered features
-> Versioned feature store
-> Recommendation training and inference
```

## Stage 1: ingestion and raw storage

Products, users, and carts are collected through DummyJSON APIs. Clickstream events are collected from a local CSV.

```text
DummyJSON products/users/carts -> retrying API client -> immutable JSON snapshots
Clickstream CSV -> required-column validation -> immutable CSV snapshot
Both sources -> logs + run manifest + checksums
```

Raw snapshots are stored under:

```text
data/raw/<source>/<entity>/ingestion_date=YYYY-MM-DD/
```

Every artifact has a timestamped filename, SHA-256 checksum, record count, source location, and run metadata. Downstream stages never edit raw snapshots.

## Stage 2: validation quality gate

Stage 2 reads the latest immutable snapshot for each required entity.

```text
Latest raw snapshots
-> profile schema and missing values
-> validate types, ranges, formats, duplicates, and references
-> route records
-> prepared valid data or quarantine data
-> JSON and PDF quality reports
```

Products and users are validated first. Their valid identifiers become trusted reference sets for cart and event validation.

Invalid records retain original source fields and receive:

- `_source_row_number`
- `_validation_errors`
- Rule name, field, message, and offending value

## Stage 3: preparation and EDA

Only validated Stage 2 data is used.

```text
Prepared JSON
-> flatten nested products and cart items
-> standardise IDs, text, numeric values, and timestamps
-> encode selected categorical values
-> min-max normalise selected numerical values
-> create sparse interactions and popularity data
-> Parquet datasets, EDA charts, and summary
```

Processed datasets:

- `products`
- `users`
- `carts`
- `cart_items`
- `events`
- `interactions`
- `product_popularity`

Passwords, SSNs, bank data, and crypto data are excluded from processed user records.

Unobserved user-product pairs are not stored as dense records. They are treated as implicit zero-feedback, preserving sparse data suitable for recommenders.

## Stage 4: DuckDB warehouse and feature engineering

Stage 4 loads the latest Parquet files into:

```text
data/warehouse/recomart.db
```

Warehouse tables:

- Dimensions: `dim_users`, `dim_products`
- Facts: `fact_carts`, `fact_cart_items`, `fact_events`, `fact_interactions`
- Features: `feature_user_activity`, `feature_product_popularity`, `feature_user_product`, `feature_product_cooccurrence`

The logical schema is documented in `docs/warehouse_schema.sql`.

Feature logic:

- **User activity**: interaction count, distinct products, total quantity, active event days, and average catalogue rating of interacted products.
- **Product popularity**: interaction count, unique-user count, total quantity, category, price, and catalogue rating.
- **User-product score**: implicit weights: view = 1, click = 2, cart = 3, purchase = 4.
- **Product co-occurrence**: distinct-cart count for each product pair.

## Stage 5: versioned feature store

The feature store is intentionally separate from the warehouse.

```text
data/warehou