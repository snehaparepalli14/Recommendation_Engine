from __future__ import annotations

import csv
import json
import logging
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from recomart.config import ProjectConfig
from recomart.validation.reporting import write_json_report, write_pdf_report

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_EVENT_TYPES = {"view", "click", "cart", "purchase"}


def is_missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and not value.strip()
    )


def as_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    return None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None

    return None


def validation_error(
    rule: str,
    field: str,
    message: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "field": field,
        "message": message,
        "value": value,
    }


def require_field(
    errors: list[dict[str, Any]],
    record: dict[str, Any],
    field: str,
) -> None:
    if is_missing(record.get(field)):
        errors.append(
            validation_error(
                "missing_required",
                field,
                f"{field} is required",
                record.get(field),
            )
        )


def require_positive_integer(
    errors: list[dict[str, Any]],
    value: Any,
    field: str,
    required: bool = True,
) -> int | None:
    if is_missing(value):
        if required:
            errors.append(
                validation_error(
                    "missing_required",
                    field,
                    f"{field} is required",
                    value,
                )
            )
        return None

    converted = as_integer(value)

    if converted is None:
        errors.append(
            validation_error(
                "type",
                field,
                f"{field} must be an integer",
                value,
            )
        )
        return None

    if converted <= 0:
        errors.append(
            validation_error(
                "range",
                field,
                f"{field} must be greater than zero",
                value,
            )
        )

    return converted


def check_non_negative_number(
    errors: list[dict[str, Any]],
    value: Any,
    field: str,
) -> None:
    if is_missing(value):
        return

    converted = as_number(value)

    if converted is None:
        errors.append(
            validation_error(
                "type",
                field,
                f"{field} must be numeric",
                value,
            )
        )
    elif converted < 0:
        errors.append(
            validation_error(
                "range",
                field,
                f"{field} must be zero or greater",
                value,
            )
        )


def duplicate_positions(
    records: list[dict[str, Any]],
    field: str,
) -> set[int]:
    positions_by_value: defaultdict[int, list[int]] = defaultdict(list)

    for position, record in enumerate(records):
        identifier = as_integer(record.get(field))
        if identifier is not None:
            positions_by_value[identifier].append(position)

    return {
        position
        for positions in positions_by_value.values()
        if len(positions) > 1
        for position in positions
    }


def validate_products(
    records: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    duplicates = duplicate_positions(records, "id")
    results: list[list[dict[str, Any]]] = []

    for position, record in enumerate(records):
        errors: list[dict[str, Any]] = []

        require_positive_integer(errors, record.get("id"), "id")
        require_field(errors, record, "title")
        require_field(errors, record, "category")

        price = record.get("price")
        if is_missing(price):
            errors.append(
                validation_error(
                    "missing_required",
                    "price",
                    "price is required",
                    price,
                )
            )
        elif as_number(price) is None:
            errors.append(
                validation_error("type", "price", "price must be numeric", price)
            )
        elif as_number(price) <= 0:
            errors.append(
                validation_error(
                    "range",
                    "price",
                    "price must be greater than zero",
                    price,
                )
            )

        rating = record.get("rating")
        if not is_missing(rating):
            if as_number(rating) is None:
                errors.append(
                    validation_error(
                        "type",
                        "rating",
                        "rating must be numeric",
                        rating,
                    )
                )
            elif not 0 <= as_number(rating) <= 5:
                errors.append(
                    validation_error(
                        "range",
                        "rating",
                        "rating must be between 0 and 5",
                        rating,
                    )
                )

        check_non_negative_number(errors, record.get("stock"), "stock")

        for field in ("tags", "images"):
            if field in record and not isinstance(record[field], list):
                errors.append(
                    validation_error(
                        "type",
                        field,
                        f"{field} must be a list",
                        record[field],
                    )
                )

        if position in duplicates:
            errors.append(
                validation_error(
                    "duplicate",
                    "id",
                    "product id must be unique",
                    record.get("id"),
                )
            )

        results.append(errors)

    return results


def validate_users(
    records: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    duplicates = duplicate_positions(records, "id")
    results: list[list[dict[str, Any]]] = []

    for position, record in enumerate(records):
        errors: list[dict[str, Any]] = []

        require_positive_integer(errors, record.get("id"), "id")

        for field in ("username", "email", "firstName", "lastName"):
            require_field(errors, record, field)

        email = record.get("email")
        if not is_missing(email):
            if not isinstance(email, str) or not EMAIL_PATTERN.fullmatch(email.strip()):
                errors.append(
                    validation_error(
                        "format",
                        "email",
                        "email must have a valid format",
                        email,
                    )
                )

        if not is_missing(record.get("age")):
            require_positive_integer(
                errors,
                record.get("age"),
                "age",
                required=False,
            )

        if position in duplicates:
            errors.append(
                validation_error(
                    "duplicate",
                    "id",
                    "user id must be unique",
                    record.get("id"),
                )
            )

        results.append(errors)

    return results


def validate_carts(
    records: list[dict[str, Any]],
    valid_user_ids: set[int],
    valid_product_ids: set[int],
) -> list[list[dict[str, Any]]]:
    duplicates = duplicate_positions(records, "id")
    results: list[list[dict[str, Any]]] = []

    for position, record in enumerate(records):
        errors: list[dict[str, Any]] = []

        require_positive_integer(errors, record.get("id"), "id")

        user_id = require_positive_integer(
            errors,
            record.get("userId"),
            "userId",
        )

        if user_id is not None and user_id not in valid_user_ids:
            errors.append(
                validation_error(
                    "referential_integrity",
                    "userId",
                    "userId does not exist in valid users",
                    record.get("userId"),
                )
            )

        products = record.get("products")

        if not isinstance(products, list):
            errors.append(
                validation_error(
                    "type",
                    "products",
                    "products must be a list",
                    products,
                )
            )
        elif not products:
            errors.append(
                validation_error(
                    "missing_required",
                    "products",
                    "products must be a non-empty list",
                    products,
                )
            )
        else:
            for item_number, item in enumerate(products):
                prefix = f"products[{item_number}]"

                if not isinstance(item, dict):
                    errors.append(
                        validation_error(
                            "type",
                            prefix,
                            "each cart product must be an object",
                            item,
                        )
                    )
                    continue

                product_id = require_positive_integer(
                    errors,
                    item.get("id"),
                    f"{prefix}.id",
                )

                if product_id is not None and product_id not in valid_product_ids:
                    errors.append(
                        validation_error(
                            "referential_integrity",
                            f"{prefix}.id",
                            "product ID does not exist in valid products",
                            item.get("id"),
                        )
                    )

                require_positive_integer(
                    errors,
                    item.get("quantity"),
                    f"{prefix}.quantity",
                )

        for field in (
            "total",
            "discountedTotal",
            "totalProducts",
            "totalQuantity",
        ):
            check_non_negative_number(errors, record.get(field), field)

        if position in duplicates:
            errors.append(
                validation_error(
                    "duplicate",
                    "id",
                    "cart id must be unique",
                    record.get("id"),
                )
            )

        results.append(errors)

    return results


def validate_events(
    records: list[dict[str, Any]],
    valid_user_ids: set[int],
    valid_product_ids: set[int],
) -> list[list[dict[str, Any]]]:
    event_ids = Counter(
        str(record.get("event_id"))
        for record in records
        if not is_missing(record.get("event_id"))
    )

    results: list[list[dict[str, Any]]] = []

    for record in records:
        errors: list[dict[str, Any]] = []

        require_field(errors, record, "event_id")

        if (
            not is_missing(record.get("event_id"))
            and event_ids[str(record.get("event_id"))] > 1
        ):
            errors.append(
                validation_error(
                    "duplicate",
                    "event_id",
                    "event_id must be unique",
                    record.get("event_id"),
                )
            )

        user_id = require_positive_integer(
            errors,
            record.get("user_id"),
            "user_id",
        )
        product_id = require_positive_integer(
            errors,
            record.get("product_id"),
            "product_id",
        )

        if user_id is not None and user_id not in valid_user_ids:
            errors.append(
                validation_error(
                    "referential_integrity",
                    "user_id",
                    "user_id does not exist in valid users",
                    record.get("user_id"),
                )
            )

        if product_id is not None and product_id not in valid_product_ids:
            errors.append(
                validation_error(
                    "referential_integrity",
                    "product_id",
                    "product_id does not exist in valid products",
                    record.get("product_id"),
                )
            )

        event_type = record.get("event_type")

        if is_missing(event_type):
            errors.append(
                validation_error(
                    "missing_required",
                    "event_type",
                    "event_type is required",
                    event_type,
                )
            )
        elif event_type not in ALLOWED_EVENT_TYPES:
            errors.append(
                validation_error(
                    "format",
                    "event_type",
                    "event_type must be view, click, cart, or purchase",
                    event_type,
                )
            )

        timestamp = record.get("event_timestamp")

        if is_missing(timestamp):
            errors.append(
                validation_error(
                    "missing_required",
                    "event_timestamp",
                    "event_timestamp is required",
                    timestamp,
                )
            )
        elif not isinstance(timestamp, str):
            errors.append(
                validation_error(
                    "type",
                    "event_timestamp",
                    "event_timestamp must be an ISO-8601 string",
                    timestamp,
                )
            )
        else:
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                errors.append(
                    validation_error(
                        "format",
                        "event_timestamp",
                        "event_timestamp must be valid ISO-8601",
                        timestamp,
                    )
                )

        require_field(errors, record, "session_id")
        results.append(errors)

    return results


def schema_profile(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: defaultdict[str, set[str]] = defaultdict(set)

    for record in records:
        for field, value in record.items():
            result[field].add(type(value).__name__)

    return {
        field: sorted(types)
        for field, types in sorted(result.items())
    }


def build_profile(
    entity: str,
    records: list[dict[str, Any]],
    errors_by_record: list[list[dict[str, Any]]],
    source_file: Path,
    valid_output: Path,
    quarantine_output: Path,
) -> dict[str, Any]:
    fields = sorted(
        {
            field
            for record in records
            for field in record
        }
    )

    total = len(records)
    missing_values: dict[str, dict[str, float | int]] = {}

    for field in fields:
        count = sum(is_missing(record.get(field)) for record in records)
        missing_values[field] = {
            "count": count,
            "percent": round((count / total * 100) if total else 0, 2),
        }

    failures = Counter(
        error["rule"]
        for errors in errors_by_record
        for error in errors
    )

    numeric_summary: dict[str, dict[str, float]] = {}

    for field in fields:
        values = [
            as_number(record.get(field))
            for record in records
        ]
        usable = [value for value in values if value is not None]

        if usable:
            numeric_summary[field] = {
                "min": min(usable),
                "max": max(usable),
                "mean": round(mean(usable), 4),
                "median": median(usable),
            }

    category_fields = {
        "products": ["category", "brand"],
        "users": ["gender", "role"],
        "carts": [],
        "events": ["event_type"],
    }.get(entity, [])

    distinct_values = {
        field: len(
            {
                str(record.get(field))
                for record in records
                if not is_missing(record.get(field))
            }
        )
        for field in category_fields
        if field in fields
    }

    valid_count = sum(not errors for errors in errors_by_record)
    invalid_count = total - valid_count

    observation = f"{valid_count} of {total} records passed the quality gate."

    if invalid_count:
        observation += (
            f" {invalid_count} record(s) were quarantined. "
            f"The most frequent rule failure was "
            f"'{failures.most_common(1)[0][0]}'."
        )
    else:
        observation += " No records required quarantine."

    return {
        "total_records": total,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "pass_rate_percent": round(
            (valid_count / total * 100) if total else 0,
            2,
        ),
        "duplicate_count": failures.get("duplicate", 0),
        "missing_values": missing_values,
        "rule_failures": dict(sorted(failures.items())),
        "schema": schema_profile(records),
        "numeric_summary": numeric_summary,
        "distinct_value_counts": distinct_values,
        "source_file": str(source_file),
        "valid_output": str(valid_output),
        "quarantine_output": str(quarantine_output),
        "observation": observation,
    }


def latest_snapshot(
    raw_dir: Path,
    source: str,
    entity: str,
    suffix: str,
) -> Path:
    candidates = list(
        (raw_dir / source / entity).glob(
            f"ingestion_date=*/*{suffix}"
        )
    )

    if not candidates:
        raise FileNotFoundError(
            f"No raw {entity} snapshot found under "
            f"{raw_dir / source / entity}"
        )

    return max(candidates, key=lambda path: path.name)


def load_json_collection(path: Path, collection: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict) or not isinstance(
        payload.get(collection),
        list,
    ):
        raise ValueError(
            f"{path} does not contain a valid '{collection}' list"
        )

    return [
        dict(record)
        for record in payload[collection]
        if isinstance(record, dict)
    ]


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            dict(row)
            for row in csv.DictReader(handle)
        ]


def write_records(
    root: Path,
    entity: str,
    records: list[dict[str, Any]],
    validation_time: datetime,
) -> Path:
    directory = (
        root
        / entity
        / f"validation_date={validation_time.date().isoformat()}"
    )
    directory.mkdir(parents=True, exist_ok=True)

    filename = (
        f"{entity}_"
        f"{validation_time.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    )
    destination = directory / filename

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return destination


def route_records(
    records: list[dict[str, Any]],
    errors_by_record: list[list[dict[str, Any]]],
    source_row_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid_records: list[dict[str, Any]] = []
    invalid_records: list[dict[str, Any]] = []

    for offset, (record, errors) in enumerate(
        zip(records, errors_by_record)
    ):
        if errors:
            rejected_record = dict(record)
            rejected_record["_source_row_number"] = source_row_start + offset
            rejected_record["_validation_errors"] = errors
            invalid_records.append(rejected_record)
        else:
            valid_records.append(dict(record))

    return valid_records, invalid_records


def valid_ids(
    records: list[dict[str, Any]],
    errors_by_record: list[list[dict[str, Any]]],
) -> set[int]:
    identifiers: set[int] = set()

    for record, errors in zip(records, errors_by_record):
        identifier = as_integer(record.get("id"))

        if not errors and identifier is not None:
            identifiers.add(identifier)

    return identifiers


def validate_latest_raw_snapshots(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    validation_time = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    logger.info(
        "pipeline_started run_id=%s stage=validation",
        run_id,
    )

    source_paths = {
        "products": latest_snapshot(
            config.raw_dir,
            "dummyjson",
            "products",
            ".json",
        ),
        "users": latest_snapshot(
            config.raw_dir,
            "dummyjson",
            "users",
            ".json",
        ),
        "carts": latest_snapshot(
            config.raw_dir,
            "dummyjson",
            "carts",
            ".json",
        ),
        "events": latest_snapshot(
            config.raw_dir,
            "clickstream",
            "events",
            ".csv",
        ),
    }

    records = {
        "products": load_json_collection(
            source_paths["products"],
            "products",
        ),
        "users": load_json_collection(
            source_paths["users"],
            "users",
        ),
        "carts": load_json_collection(
            source_paths["carts"],
            "carts",
        ),
        "events": load_events(source_paths["events"]),
    }

    errors = {
        "products": validate_products(records["products"]),
        "users": validate_users(records["users"]),
    }

    trusted_product_ids = valid_ids(
        records["products"],
        errors["products"],
    )
    trusted_user_ids = valid_ids(
        records["users"],
        errors["users"],
    )

    errors["carts"] = validate_carts(
        records["carts"],
        trusted_user_ids,
        trusted_product_ids,
    )
    errors["events"] = validate_events(
        records["events"],
        trusted_user_ids,
        trusted_product_ids,
    )

    profiles: dict[str, dict[str, Any]] = {}

    for entity in ("products", "users", "carts", "events"):
        valid_records, invalid_records = route_records(
            records[entity],
            errors[entity],
            source_row_start=2 if entity == "events" else 1,
        )

        valid_output = write_records(
            config.prepared_dir,
            entity,
            valid_records,
            validation_time,
        )
        quarantine_output = write_records(
            config.quarantine_dir,
            entity,
            invalid_records,
            validation_time,
        )

        profiles[entity] = build_profile(
            entity,
            records[entity],
            errors[entity],
            source_paths[entity],
            valid_output,
            quarantine_output,
        )

        logger.info(
            "validation_routed run_id=%s entity=%s valid=%s invalid=%s",
            run_id,
            entity,
            len(valid_records),
            len(invalid_records),
        )

    invalid_total = sum(
        profile["invalid_records"]
        for profile in profiles.values()
    )

    report = {
        "project": "RecoMart",
        "stage": "data_profiling_and_validation",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed_with_issues" if invalid_total else "passed",
        "quality_gate": {
            "invalid_records": invalid_total,
            "critical_inputs_loaded": True,
        },
        "datasets": profiles,
    }

    json_path = config.reports_dir / f"data_quality_{run_id}.json"
    pdf_path = config.reports_dir / f"data_quality_{run_id}.pdf"

    write_json_report(json_path, report)
    write_pdf_report(pdf_path, report)

    report["json_report"] = str(json_path)
    report["pdf_report"] = str(pdf_path)

    logger.info(
        "pipeline_finished run_id=%s stage=validation status=%s",
        run_id,
        report["status"],
    )

    return report