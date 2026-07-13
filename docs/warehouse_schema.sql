-- RecoMart logical analytics schema.
-- The pipeline creates these tables from the latest Stage 3 Parquet files.

CREATE TABLE dim_products (
    product_id BIGINT PRIMARY KEY,
    title VARCHAR,
    category VARCHAR,
    category_code BIGINT,
    price DOUBLE,
    price_normalized DOUBLE,
    rating DOUBLE,
    stock DOUBLE
);

CREATE TABLE dim_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR,
    age DOUBLE,
    age_normalized DOUBLE,
    gender VARCHAR,
    gender_code BIGINT,
    country VARCHAR,
    country_code BIGINT
);

CREATE TABLE fact_carts (
    cart_id BIGINT PRIMARY KEY,
    user_id BIGINT,
    total DOUBLE,
    discounted_total DOUBLE,
    total_quantity DOUBLE
);

CREATE TABLE fact_cart_items (
    cart_id BIGINT,
    user_id BIGINT,
    product_id BIGINT,
    quantity DOUBLE,
    item_total DOUBLE
);

CREATE TABLE fact_events (
    event_id VARCHAR PRIMARY KEY,
    user_id BIGINT,
    product_id BIGINT,
    event_type VARCHAR,
    event_timestamp TIMESTAMP,
    session_id VARCHAR
);

CREATE TABLE fact_interactions (
    user_id BIGINT,
    product_id BIGINT,
    event_type VARCHAR,
    event_timestamp TIMESTAMP,
    quantity DOUBLE,
    source VARCHAR,
    observed_interaction INTEGER
);

CREATE TABLE feature_user_activity (
    user_id BIGINT,
    interaction_count BIGINT,
    distinct_product_count BIGINT,
    total_interaction_quantity DOUBLE,
    average_interacted_product_rating DOUBLE,
    active_event_days BIGINT
);

CREATE TABLE feature_product_popularity (
    product_id BIGINT,
    interaction_count BIGINT,
    unique_user_count BIGINT,
    total_interaction_quantity DOUBLE,
    catalogue_rating DOUBLE
);

CREATE TABLE feature_user_product (
    user_id BIGINT,
    product_id BIGINT,
    interaction_count BIGINT,
    total_quantity DOUBLE,
    weighted_interaction_score DOUBLE,
    last_event_timestamp TIMESTAMP
);

CREATE TABLE feature_product_cooccurrence (
    product_id_left BIGINT,
    product_id_right BIGINT,
    cart_cooccurrence_count BIGINT
);