"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from recomart.config import load_config
from recomart.logging_config import configure_logging
from recomart.pipeline import (
    run_ingestion,
    run_preparation_eda,
    run_validation,
    run_features,
    get_user_features,
    run_feature_store,
)

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recomart",
        description="RecoMart data-management pipeline",
    )

    parser.add_argument(
        "command",
        choices=["ingest-all","validate-all","prepare-eda","build-features","materialize-feature-store","get-user-features",],
        help="Pipeline command to execute",
    )

    parser.add_argument("--user-id", type=int)
    parser.add_argument(
        "--consumer",
        choices=["training", "inference"],
        default="inference",
    )

    args = parser.parse_args(argv)
    config = load_config()
    logger = configure_logging(config.log_file)

    if args.command == "ingest-all":
        result = run_ingestion(config, logger)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "validate-all":
        result = run_validation(config, logger)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "prepare-eda":
        result = run_preparation_eda(config, logger)
        print(json.dumps(result, indent=2))
        return 0
    
    if args.command == "build-features":
        result = run_features(config, logger)
        print(json.dumps(result, indent=2))
        return 0
    
    if args.command == "materialize-feature-store":
        result = run_feature_store(config, logger)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "get-user-features":
        if args.user_id is None:
            parser.error("--user-id is required for get-user-features")

        result = get_user_features(
            config,
            args.user_id,
            args.consumer,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0
    

    return 2