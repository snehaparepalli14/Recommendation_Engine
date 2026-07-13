from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from recomart.config import ProjectConfig

def add_category_codes(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Add deterministic integer codes while retaining readable values."""
    output = frame.copy()

    for column in columns:
        values = output[column].astype("string").fillna("unknown")
        categories = sorted(values.unique().tolist())
        mapping = {
            value: position
            for position, value in enumerate(categories)
        }
        output[f"{column}_code"] = values.map(mapping).astype("Int64")

    return output


def min_max_normalize(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Add 0-1 scaled columns while retaining original values."""
    output = frame.copy()

    for column in columns:
        values = pd.to_numeric(output[column], errors="coerce")
        usable = values.dropna()

        if usable.empty or usable.min() == usable.max():
            output[f"{column}_normalized"] = values.where(
                values.isna(),
                0.0,
            )
        else:
            output[f"{column}_normalized"] = (
                (values - usable.min())
                / (usable.max() - usable.min())
            )

    return output

def latest_prepared_file(prepared_dir: Path, entity: str) -> Path:
    candidates = list(
        (prepared_dir / entity).glob("validation_date=*/*.json")
    )

    if not candidates:
        raise FileNotFoundError(
            f"No validated prepared file found for entity: {entity}"
        )

    return max(candidates, key=lambda path: path.name)


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)

    if not isinstance(records, list):
        raise ValueError(f"Prepared file is not a JSON list: {path}")

    return [
        dict(record)
        for record in records
        if isinstance(record, dict)
    ]


def select_columns(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    output = pd.DataFrame()

    for column in columns:
        if column in frame.columns:
            output[column] = frame[column]
        else:
            output[column] = pd.NA

    return output


def clean_products(records: list[dict[str, Any]]) -> pd.DataFrame:
    raw = pd.json_normalize(records)

    products = select_columns(
        raw,
        [
            "id",
            "title",
            "description",
            "category",
            "brand",
            "price",
            "rating",
            "stock",
            "tags",
            "thumbnail",
            "dimensions.width",
            "dimensions.height",
            "dimensions.depth",
        ],
    )

    products = products.rename(
        columns={
            "id": "product_id",
            "dimensions.width": "dimension_width",
            "dimensions.height": "dimension_height",
            "dimensions.depth": "dimension_depth",
        }
    )

    products["product_id"] = pd.to_numeric(
        products["product_id"],
        errors="coerce",
    ).astype("Int64")

    for column in (
        "price",
        "rating",
        "stock",
        "dimension_width",
        "dimension_height",
        "dimension_depth",
    ):
        products[column] = pd.to_numeric(
            products[column],
            errors="coerce",
        )

    products["category"] = (
        products["category"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    products["brand"] = (
        products["brand"]
        .astype("string")
        .str.strip()
        .fillna("unknown")
    )

    products["tags"] = products["tags"].apply(
        lambda value: "|".join(str(item) for item in value)
        if isinstance(value, list)
        else ""
    )

    products = add_category_codes(products, ["category", "brand"])
    products = min_max_normalize(products, ["price", "rating", "stock"])

    return products.sort_values("product_id").reset_index(drop=True)

def clean_users(records: list[dict[str, Any]]) -> pd.DataFrame:
    raw = pd.json_normalize(records)

    users = select_columns(
        raw,
        [
            "id",
            "username",
            "firstName",
            "lastName",
            "email",
            "age",
            "gender",
            "address.city",
            "address.state",
            "address.country",
            "company.department",
        ],
    )

    users = users.rename(
        columns={
            "id": "user_id",
            "firstName": "first_name",
            "lastName": "last_name",
            "address.city": "city",
            "address.state": "state",
            "address.country": "country",
            "company.department": "company_department",
        }
    )

    users["user_id"] = pd.to_numeric(
        users["user_id"],
        errors="coerce",
    ).astype("Int64")

    users["age"] = pd.to_numeric(
        users["age"],
        errors="coerce",
    )

    users["gender"] = (
        users["gender"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    users = add_category_codes(
        users,
        ["gender", "country", "company_department"],
    )
    users = min_max_normalize(users, ["age"])

    return users.sort_values("user_id").reset_index(drop=True)


def clean_carts(
    records: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cart_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []

    for record in records:
        cart_id = record.get("id")
        user_id = record.get("userId")

        cart_rows.append(
            {
                "cart_id": cart_id,
                "user_id": user_id,
                "total": record.get("total"),
                "discounted_total": record.get("discountedTotal"),
                "total_products": record.get("totalProducts"),
                "total_quantity": record.get("totalQuantity"),
            }
        )

        for item in record.get("products", []):
            if isinstance(item, dict):
                item_rows.append(
                    {
                        "cart_id": cart_id,
                        "user_id": user_id,
                        "product_id": item.get("id"),
                        "quantity": item.get("quantity"),
                        "item_total": item.get("total"),
                        "discounted_item_total": item.get(
                            "discountedTotal"
                        ),
                    }
                )

    carts = pd.DataFrame(
        cart_rows,
        columns=[
            "cart_id",
            "user_id",
            "total",
            "discounted_total",
            "total_products",
            "total_quantity",
        ],
    )
    cart_items = pd.DataFrame(
        item_rows,
        columns=[
            "cart_id",
            "user_id",
            "product_id",
            "quantity",
            "item_total",
            "discounted_item_total",
        ],
    )

    for frame, id_columns in (
        (carts, ["cart_id", "user_id"]),
        (cart_items, ["cart_id", "user_id", "product_id"]),
    ):
        for column in id_columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            ).astype("Int64")

    for column in (
        "total",
        "discounted_total",
        "total_products",
        "total_quantity",
    ):
        carts[column] = pd.to_numeric(carts[column], errors="coerce")

    for column in (
        "quantity",
        "item_total",
        "discounted_item_total",
    ):
        cart_items[column] = pd.to_numeric(
            cart_items[column],
            errors="coerce",
        )

    carts = min_max_normalize(carts, ["total", "discounted_total"])
    cart_items = min_max_normalize(
        cart_items,
        ["quantity", "item_total", "discounted_item_total"],
    )

    return carts, cart_items

def clean_events(records: list[dict[str, Any]]) -> pd.DataFrame:
    events = pd.DataFrame(records)

    events = select_columns(
        events,
        [
            "event_id",
            "user_id",
            "product_id",
            "event_type",
            "event_timestamp",
            "session_id",
        ],
    )

    events["user_id"] = pd.to_numeric(
        events["user_id"],
        errors="coerce",
    ).astype("Int64")

    events["product_id"] = pd.to_numeric(
        events["product_id"],
        errors="coerce",
    ).astype("Int64")

    events["event_type"] = (
        events["event_type"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    events["event_timestamp"] = pd.to_datetime(
        events["event_timestamp"],
        utc=True,
        errors="coerce",
    )

    return events.sort_values("event_timestamp").reset_index(drop=True)


def create_interactions(
    events: pd.DataFrame,
    cart_items: pd.DataFrame,
) -> pd.DataFrame:
    event_interactions = events[
        [
            "user_id",
            "product_id",
            "event_type",
            "event_timestamp",
            "session_id",
        ]
    ].copy()

    event_interactions["quantity"] = 1
    event_interactions["source"] = "clickstream"
    event_interactions["observed_interaction"] = 1

    cart_interactions = cart_items[
        ["user_id", "product_id", "quantity"]
    ].copy()

    cart_interactions["event_type"] = "cart"
    cart_interactions["event_timestamp"] = pd.NaT
    cart_interactions["session_id"] = pd.NA
    cart_interactions["source"] = "cart_snapshot"
    cart_interactions["observed_interaction"] = 1

    cart_interactions = cart_interactions[
        [
            "user_id",
            "product_id",
            "event_type",
            "event_timestamp",
            "session_id",
            "quantity",
            "source",
            "observed_interaction",
        ]
    ]

    return pd.concat(
        [event_interactions, cart_interactions],
        ignore_index=True,
    )


def save_plot(figure: plt.Figure, output: Path) -> None:
    figure.tight_layout()
    figure.savefig(output, dpi=150, bbox_inches="tight")
    plt.close(figure)


def create_eda_plots(
    products: pd.DataFrame,
    events: pd.DataFrame,
    interactions: pd.DataFrame,
    popularity: pd.DataFrame,
    output_dir: Path,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[str] = []

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(products["price"].dropna(), bins=30, color="#1f77b4")
    axis.set_title("Product Price Distribution")
    axis.set_xlabel("Price")
    axis.set_ylabel("Number of products")
    path = output_dir / "price_distribution.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    category_counts = products["category"].value_counts().head(12)

    figure, axis = plt.subplots(figsize=(9, 5))
    category_counts.sort_values().plot.barh(
        ax=axis,
        color="#2a9d8f",
    )
    axis.set_title("Top Product Categories")
    axis.set_xlabel("Number of products")
    axis.set_ylabel("Category")
    path = output_dir / "category_distribution.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(
        products["rating"].dropna(),
        bins=15,
        color="#e76f51",
    )
    axis.set_title("Product Rating Distribution")
    axis.set_xlabel("Rating")
    axis.set_ylabel("Number of products")
    path = output_dir / "ratings_distribution.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    top_popularity = popularity.head(10).sort_values(
        "interaction_count"
    )

    figure, axis = plt.subplots(figsize=(9, 5))
    axis.barh(
        top_popularity["title"].fillna("Unknown product"),
        top_popularity["interaction_count"],
        color="#457b9d",
    )
    axis.set_title("Top Products by Interaction Count")
    axis.set_xlabel("Interactions")
    axis.set_ylabel("Product")
    path = output_dir / "product_popularity.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    interactions_per_user = interactions.groupby("user_id").size()

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.hist(
        interactions_per_user,
        bins=20,
        color="#6a4c93",
    )
    axis.set_title("Interactions per User")
    axis.set_xlabel("Number of interactions")
    axis.set_ylabel("Number of users")
    path = output_dir / "interactions_per_user.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    event_counts = events["event_type"].value_counts()

    figure, axis = plt.subplots(figsize=(7, 5))
    event_counts.plot.bar(ax=axis, color="#f4a261")
    axis.set_title("Clickstream Event-Type Distribution")
    axis.set_xlabel("Event type")
    axis.set_ylabel("Number of events")
    axis.tick_params(axis="x", rotation=0)
    path = output_dir / "event_type_distribution.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    unique_pairs = interactions[
        ["user_id", "product_id"]
    ].drop_duplicates()

    figure, axis = plt.subplots(figsize=(9, 5))
    axis.scatter(
        unique_pairs["product_id"],
        unique_pairs["user_id"],
        s=8,
        alpha=0.65,
        color="#264653",
    )
    axis.set_title("User-Item Interaction Matrix Sparsity")
    axis.set_xlabel("Product ID")
    axis.set_ylabel("User ID")
    path = output_dir / "user_item_sparsity.png"
    save_plot(figure, path)
    output_paths.append(str(path))

    return output_paths


def write_summary(
    destination: Path,
    summary: dict[str, Any],
) -> None:
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


def run_preparation_and_eda(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    logger.info(
        "pipeline_started run_id=%s stage=preparation_eda",
        run_id,
    )

    source_paths = {
        entity: latest_prepared_file(config.prepared_dir, entity)
        for entity in ("products", "users", "carts", "events")
    }

    product_records = load_records(source_paths["products"])
    user_records = load_records(source_paths["users"])
    cart_records = load_records(source_paths["carts"])
    event_records = load_records(source_paths["events"])

    products = clean_products(product_records)
    users = clean_users(user_records)
    carts, cart_items = clean_carts(cart_records)
    events = clean_events(event_records)
    interactions = create_interactions(events, cart_items)

    popularity = (
        interactions.groupby("product_id")
        .agg(
            interaction_count=("product_id", "size"),
            unique_users=("user_id", "nunique"),
            total_quantity=("quantity", "sum"),
        )
        .reset_index()
        .merge(
            products[["product_id", "title", "category"]],
            on="product_id",
            how="left",
        )
        .sort_values(
            ["interaction_count", "total_quantity"],
            ascending=False,
        )
        .reset_index(drop=True)
    )

    processed_dir = (
        config.project_root
        / "data"
        / "processed"
        / f"preparation_date={started_at.date().isoformat()}"
    )
    processed_dir.mkdir(parents=True, exist_ok=True)

    timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")

    datasets = {
        "products": products,
        "users": users,
        "carts": carts,
        "cart_items": cart_items,
        "events": events,
        "interactions": interactions,
        "product_popularity": popularity,
    }

    processed_outputs: dict[str, str] = {}

    for name, dataset in datasets.items():
        destination = processed_dir / f"{name}_{timestamp}.parquet"
        dataset.to_parquet(destination, index=False)
        processed_outputs[name] = str(destination)

    eda_dir = (
        config.project_root
        / "reports"
        / "eda"
        / f"run_id={run_id}"
    )

    plot_paths = create_eda_plots(
        products,
        events,
        interactions,
        popularity,
        eda_dir,
    )

    unique_pairs = interactions[
        ["user_id", "product_id"]
    ].drop_duplicates()

    possible_pairs = len(users) * len(products)

    sparsity_percent = round(
        100 * (1 - len(unique_pairs) / possible_pairs)
        if possible_pairs
        else 0,
        4,
    )

    summary = {
        "project": "RecoMart",
        "stage": "data_preparation_and_eda",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": {
            entity: str(path)
            for entity, path in source_paths.items()
        },
        "row_counts": {
            name: int(len(dataset))
            for name, dataset in datasets.items()
        },
        "processed_outputs": processed_outputs,
        "plots": plot_paths,
        "observations": {
            "product_categories": int(products["category"].nunique()),
            "event_types": int(events["event_type"].nunique()),
            "user_item_unique_pairs": int(len(unique_pairs)),
            "user_item_matrix_sparsity_percent": sparsity_percent,
                        "implicit_zero_interactions": int(
                possible_pairs - len(unique_pairs)
            ),
            "implicit_feedback_policy": (
                "Only observed user-product pairs are stored. All other "
                "possible pairs are treated as implicit zero-feedback "
                "interactions to preserve a sparse representation."
            ),
            "note": (
                "Sensitive user fields such as password, SSN, bank, "
                "and crypto details were excluded from processed data."
            ),
        },
    }

    summary_path = eda_dir / "eda_summary.json"
    write_summary(summary_path, summary)
    summary["summary_report"] = str(summary_path)

    logger.info(
        "pipeline_finished run_id=%s stage=preparation_eda "
        "products=%s users=%s interactions=%s",
        run_id,
        len(products),
        len(users),
        len(interactions),
    )

    return summary