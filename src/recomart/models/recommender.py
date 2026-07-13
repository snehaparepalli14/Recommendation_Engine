"""Collaborative SVD recommender training, evaluation, and inference."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from recomart.config import ProjectConfig


MODEL_VERSION = "v1"
FEATURE_STORE_VERSION = "v1"


def feature_store_database(config: ProjectConfig) -> Path:
    return (
        config.project_root
        / "data"
        / "feature_store"
        / "recomart_feature_store.db"
    )


def model_directory(config: ProjectConfig) -> Path:
    return config.project_root / "models" / "recommender"


def load_training_data(
    config: ProjectConfig,
) -> tuple[list[tuple[int, int, float]], list[int]]:
    """Read collaborative-filtering interactions from feature-store v1."""
    database_path = feature_store_database(config)

    if not database_path.exists():
        raise FileNotFoundError(
            "Feature store does not exist. Run materialize-feature-store first."
        )

    connection = duckdb.connect(str(database_path), read_only=True)

    try:
        interaction_rows = connection.execute(
            """
            SELECT
                user_id,
                product_id,
                CAST(weighted_interaction_score AS DOUBLE) AS score
            FROM user_product_v1
            WHERE weighted_interaction_score > 0
            """
        ).fetchall()

        product_rows = connection.execute(
            """
            SELECT product_id
            FROM product_popularity_v1
            ORDER BY product_id
            """
        ).fetchall()
    finally:
        connection.close()

    interactions = [
        (int(user_id), int(product_id), float(score))
        for user_id, product_id, score in interaction_rows
    ]
    product_ids = [int(row[0]) for row in product_rows]

    if not interactions:
        raise ValueError("No positive user-product interactions are available.")

    if not product_ids:
        raise ValueError("No products are available in feature-store v1.")

    return interactions, product_ids


def split_interactions(
    interactions: list[tuple[int, int, float]],
    seed: int,
) -> tuple[list[tuple[int, int, float]], dict[int, int]]:
    """Hold out one product per eligible user for deterministic ranking tests."""
    by_user: dict[int, list[tuple[int, float]]] = {}

    for user_id, product_id, score in interactions:
        by_user.setdefault(user_id, []).append((product_id, score))

    random = np.random.default_rng(seed)
    training: list[tuple[int, int, float]] = []
    held_out: dict[int, int] = {}

    for user_id in sorted(by_user):
        products = sorted(by_user[user_id], key=lambda row: row[0])

        if len(products) < 2:
            training.extend(
                (user_id, product_id, score)
                for product_id, score in products
            )
            continue

        test_index = int(random.integers(0, len(products)))
        held_out[user_id] = products[test_index][0]

        training.extend(
            (user_id, product_id, score)
            for index, (product_id, score) in enumerate(products)
            if index != test_index
        )

    return training, held_out


def create_matrix(
    interactions: list[tuple[int, int, float]],
    product_ids: list[int],
) -> tuple[np.ndarray, list[int], dict[int, int], dict[int, int]]:
    """Create a log-scaled sparse interaction matrix represented as NumPy."""
    user_ids = sorted({user_id for user_id, _, _ in interactions})
    user_index = {
        user_id: index
        for index, user_id in enumerate(user_ids)
    }
    product_index = {
        product_id: index
        for index, product_id in enumerate(product_ids)
    }

    matrix = np.zeros(
        (len(user_ids), len(product_ids)),
        dtype=np.float64,
    )

    for user_id, product_id, score in interactions:
        if product_id in product_index:
            matrix[
                user_index[user_id],
                product_index[product_id],
            ] = np.log1p(score)

    return matrix, user_ids, user_index, product_index


def train_svd(
    matrix: np.ndarray,
    requested_rank: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Fit truncated SVD and return user and product latent factors."""
    maximum_rank = min(matrix.shape) - 1

    if maximum_rank < 1:
        raise ValueError(
            "At least two users and two products are required for SVD."
        )

    actual_rank = min(requested_rank, maximum_rank)

    user_vectors, singular_values, item_vectors = np.linalg.svd(
        matrix,
        full_matrices=False,
    )

    square_root = np.sqrt(singular_values[:actual_rank])

    user_factors = user_vectors[:, :actual_rank] * square_root
    product_factors = item_vectors[:actual_rank, :].T * square_root

    return user_factors, product_factors, actual_rank


def popularity_scores(
    interactions: list[tuple[int, int, float]],
    product_ids: list[int],
) -> np.ndarray:
    totals = {product_id: 0.0 for product_id in product_ids}

    for _, product_id, score in interactions:
        totals[product_id] = totals.get(product_id, 0.0) + score

    return np.array(
        [totals[product_id] for product_id in product_ids],
        dtype=np.float64,
    )


def rank_products(
    scores: np.ndarray,
    product_ids: list[int],
    popularity: np.ndarray,
    excluded_products: set[int],
    limit: int,
) -> list[int]:
    """Return deterministic recommendations, excluding known training items."""
    ordered_indices = np.lexsort(
        (
            np.array(product_ids),
            -popularity,
            -scores,
        )
    )

    recommendations: list[int] = []

    for index in ordered_indices:
        product_id = product_ids[int(index)]

        if product_id not in excluded_products:
            recommendations.append(product_id)

        if len(recommendations) == limit:
            break

    return recommendations


def evaluate_model(
    user_factors: np.ndarray,
    product_factors: np.ndarray,
    user_ids: list[int],
    product_ids: list[int],
    training: list[tuple[int, int, float]],
    held_out: dict[int, int],
    popularity: np.ndarray,
    top_k: int,
) -> dict[str, float | int]:
    """Evaluate Top-K ranking quality for one held-out product per user."""
    known_by_user: dict[int, set[int]] = {}

    for user_id, product_id, _ in training:
        known_by_user.setdefault(user_id, set()).add(product_id)

    user_index = {
        user_id: index
        for index, user_id in enumerate(user_ids)
    }

    hits = 0
    reciprocal_ranks: list[float] = []
    recommended_products: set[int] = set()
    evaluated_users = 0

    for user_id, test_product_id in held_out.items():
        if user_id not in user_index:
            continue

        scores = user_factors[user_index[user_id]] @ product_factors.T
        recommendations = rank_products(
            scores=scores,
            product_ids=product_ids,
            popularity=popularity,
            excluded_products=known_by_user.get(user_id, set()),
            limit=top_k,
        )

        evaluated_users += 1
        recommended_products.update(recommendations)

        if test_product_id in recommendations:
            rank = recommendations.index(test_product_id) + 1
            hits += 1
            reciprocal_ranks.append(1.0 / np.log2(rank + 1))
        else:
            reciprocal_ranks.append(0.0)

    if evaluated_users == 0:
        raise ValueError("No users were eligible for model evaluation.")

    return {
        "evaluated_users": evaluated_users,
        f"precision_at_{top_k}": round(
            hits / (evaluated_users * top_k),
            4,
        ),
        f"recall_at_{top_k}": round(hits / evaluated_users, 4),
        f"ndcg_at_{top_k}": round(
            float(np.mean(reciprocal_ranks)),
            4,
        ),
        "catalog_coverage": round(
            len(recommended_products) / len(product_ids),
            4,
        ),
        "hit_count": hits,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def train_recommender(
    config: ProjectConfig,
    logger: logging.Logger,
    rank: int = 12,
    top_k: int = 10,
    seed: int = 42,
) -> dict[str, Any]:
    """Train, evaluate, track, and save the collaborative SVD model."""
    if rank < 1:
        raise ValueError("--rank must be at least 1.")

    if top_k < 1:
        raise ValueError("--top-k must be at least 1.")

    run_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "pipeline_started run_id=%s stage=model_training",
        run_id,
    )

    interactions, product_ids = load_training_data(config)
    training, held_out = split_interactions(interactions, seed)

    matrix, user_ids, _, _ = create_matrix(training, product_ids)
    user_factors, product_factors, actual_rank = train_svd(matrix, rank)
    popularity = popularity_scores(training, product_ids)

    metrics = evaluate_model(
        user_factors=user_factors,
        product_factors=product_factors,
        user_ids=user_ids,
        product_ids=product_ids,
        training=training,
        held_out=held_out,
        popularity=popularity,
        top_k=top_k,
    )

    known_by_user: dict[str, list[int]] = {}

    for user_id, product_id, _ in training:
        known_by_user.setdefault(str(user_id), []).append(product_id)

    for user_id in known_by_user:
        known_by_user[user_id].sort()

    output_directory = model_directory(config)
    output_directory.mkdir(parents=True, exist_ok=True)

    model_path = output_directory / f"svd_model_{MODEL_VERSION}.npz"

    np.savez_compressed(
        model_path,
        user_ids=np.array(user_ids, dtype=np.int64),
        product_ids=np.array(product_ids, dtype=np.int64),
        user_factors=user_factors,
        product_factors=product_factors,
        popularity=popularity,
    )

    evaluation_path = (
        config.project_root
        / "reports"
        / "model_evaluation"
        / f"run_id={run_id}"
        / "model_performance.json"
    )
    experiment_path = (
        config.project_root
        / "reports"
        / "experiments"
        / f"run_id={run_id}"
        / "run_metadata.json"
    )
    registry_path = output_directory / "model_registry.json"

    metadata: dict[str, Any] = {
        "project": "RecoMart",
        "run_id": run_id,
        "generated_at": generated_at,
        "tracking_tool": "custom_json_experiment_tracker",
        "model_type": "truncated_svd_collaborative_filter",
        "model_version": MODEL_VERSION,
        "feature_store_version": FEATURE_STORE_VERSION,
        "feature_source": str(feature_store_database(config)),
        "model_path": str(model_path),
        "parameters": {
            "requested_rank": rank,
            "actual_rank": actual_rank,
            "top_k": top_k,
            "random_seed": seed,
            "score_transformation": "log1p(weighted_interaction_score)",
            "holdout_strategy": (
                "One deterministic random observed product per user; "
                "remaining observations form training data."
            ),
        },
        "data_summary": {
            "total_interactions": len(interactions),
            "training_interactions": len(training),
            "held_out_interactions": len(held_out),
            "users": len(user_ids),
            "catalog_products": len(product_ids),
        },
        "metrics": metrics,
        "known_training_products_by_user": known_by_user,
    }

    write_json(evaluation_path, metadata)
    write_json(experiment_path, metadata)
    write_json(registry_path, metadata)

    logger.info(
        "pipeline_finished run_id=%s stage=model_training ndcg=%s",
        run_id,
        metrics[f"ndcg_at_{top_k}"],
    )

    return {
        "project": "RecoMart",
        "stage": "model_training_and_evaluation",
        "run_id": run_id,
        "model_type": metadata["model_type"],
        "model_path": str(model_path),
        "registry_path": str(registry_path),
        "evaluation_report": str(evaluation_path),
        "experiment_metadata": str(experiment_path),
        "metrics": metrics,
    }


def load_product_titles(
    config: ProjectConfig,
    product_ids: list[int],
) -> dict[int, str]:
    warehouse_path = (
        config.project_root
        / "data"
        / "warehouse"
        / "recomart.db"
    )

    if not warehouse_path.exists() or not product_ids:
        return {}

    placeholders = ", ".join("?" for _ in product_ids)
    connection = duckdb.connect(str(warehouse_path), read_only=True)

    try:
        rows = connection.execute(
            f"""
            SELECT product_id, title
            FROM dim_products
            WHERE product_id IN ({placeholders})
            """,
            product_ids,
        ).fetchall()
    finally:
        connection.close()

    return {
        int(product_id): str(title)
        for product_id, title in rows
    }


def recommend_products(
    config: ProjectConfig,
    user_id: int,
    limit: int = 10,
) -> dict[str, Any]:
    """Return a Top-K inference response using the registered SVD model."""
    if limit < 1:
        raise ValueError("--limit must be at least 1.")

    registry_path = model_directory(config) / "model_registry.json"

    if not registry_path.exists():
        raise FileNotFoundError(
            "No trained recommender found. Run train-model first."
        )

    with registry_path.open("r", encoding="utf-8") as handle:
        metadata = dict(json.load(handle))

    model = np.load(str(metadata["model_path"]))
    product_ids = [int(value) for value in model["product_ids"]]
    popularity = np.array(model["popularity"], dtype=np.float64)
    user_ids = [int(value) for value in model["user_ids"]]

    known_by_user = {
        int(key): set(value)
        for key, value in metadata[
            "known_training_products_by_user"
        ].items()
    }

    if user_id in user_ids:
        index = user_ids.index(user_id)
        scores = (
            model["user_factors"][index]
            @ model["product_factors"].T
        )
        excluded = known_by_user.get(user_id, set())
        recommendation_source = "svd_personalized"
    else:
        scores = popularity.copy()
        excluded = set()
        recommendation_source = "popularity_cold_start"

    recommended_ids = rank_products(
        scores=np.array(scores, dtype=np.float64),
        product_ids=product_ids,
        popularity=popularity,
        excluded_products=excluded,
        limit=limit,
    )
    titles = load_product_titles(config, recommended_ids)
    score_by_product = {
        product_id: float(scores[index])
        for index, product_id in enumerate(product_ids)
    }

    return {
        "model_run_id": metadata["run_id"],
        "model_version": metadata["model_version"],
        "user_id": user_id,
        "recommendation_source": recommendation_source,
        "recommendations": [
            {
                "rank": rank,
                "product_id": product_id,
                "title": titles.get(product_id, "Unknown product"),
                "predicted_score": round(score_by_product[product_id], 6),
            }
            for rank, product_id in enumerate(recommended_ids, start=1)
        ],
    }