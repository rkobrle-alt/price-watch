"""Pure parser for the versioned application configuration document."""

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from applications.configuration.model import ApplicationConfig
from core.configuration import ConfigurationError

_ROOT_KEYS = frozenset({"schema_version", "provider", "state", "rules", "scheduler"})


def parse_configuration(
    document: Mapping[str, object],
    base_directory: Path,
) -> ApplicationConfig:
    """Validate a schema-version-1 document without performing I/O."""
    if not isinstance(document, Mapping):
        raise TypeError("document must be a Mapping")
    if not isinstance(base_directory, Path):
        raise TypeError("base_directory must be a Path")

    _validate_keys(
        document,
        _ROOT_KEYS,
        frozenset({"schema_version", "provider", "state"}),
        "configuration",
    )
    _validate_schema_version(document["schema_version"])
    provider = _required_table(document, "provider", "provider")
    _validate_keys(provider, frozenset({"lidl"}), frozenset({"lidl"}), "provider")
    lidl = _required_table(provider, "lidl", "provider.lidl")
    _validate_keys(
        lidl,
        frozenset({"product_urls", "timeout_seconds"}),
        frozenset({"product_urls"}),
        "provider.lidl",
    )
    state = _required_table(document, "state", "state")
    _validate_keys(state, frozenset({"file"}), frozenset({"file"}), "state")

    product_urls = _product_urls(lidl["product_urls"])
    timeout_seconds = _positive_integer(
        lidl.get("timeout_seconds", 10),
        "provider.lidl.timeout_seconds",
    )
    state_file = _state_file(state["file"], base_directory)
    percentage, amount = _rules(document)
    interval = _scheduler_interval(document)

    try:
        return ApplicationConfig(
            product_urls=product_urls,
            state_file=state_file,
            timeout_seconds=timeout_seconds,
            price_drop_percentage=percentage,
            price_drop_amount=amount,
            interval=interval,
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"configuration is invalid: {error}") from error


def _validate_schema_version(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError("schema_version must be the integer 1")
    if value != 1:
        raise ConfigurationError(f"unsupported schema_version: {value}")


def _required_table(
    parent: Mapping[str, object],
    key: str,
    path: str,
) -> Mapping[str, object]:
    value = parent[key]
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path} must be a table")
    return cast(Mapping[str, object], value)


def _optional_table(
    parent: Mapping[str, object],
    key: str,
    path: str,
) -> Mapping[str, object] | None:
    if key not in parent:
        return None
    return _required_table(parent, key, path)


def _validate_keys(
    table: Mapping[object, object],
    allowed: frozenset[str],
    required: frozenset[str],
    path: str,
) -> None:
    if not all(isinstance(key, str) for key in table):
        raise ConfigurationError(f"{path} table keys must be strings")
    keys = cast(set[str], set(table))
    unknown = keys - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"{path} contains unknown keys: {names}")
    missing = required - keys
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigurationError(f"{path} is missing required keys: {names}")


def _product_urls(value: object) -> tuple[str, ...]:
    path = "provider.lidl.product_urls"
    if not isinstance(value, list) or not all(isinstance(url, str) for url in value):
        raise ConfigurationError(f"{path} must be an array of strings")
    if not value:
        raise ConfigurationError(f"{path} cannot be empty")
    if any(not url.strip() for url in value):
        raise ConfigurationError(f"{path} cannot contain blank values")
    return tuple(value)


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{path} must be a positive integer")
    if value <= 0:
        raise ConfigurationError(f"{path} must be positive")
    return value


def _state_file(value: object, base_directory: Path) -> Path:
    path = "state.file"
    if not isinstance(value, str):
        raise ConfigurationError(f"{path} must be a string")
    if not value.strip():
        raise ConfigurationError(f"{path} cannot be blank")
    state_file = Path(value)
    return state_file if state_file.is_absolute() else base_directory / state_file


def _rules(
    document: Mapping[str, object],
) -> tuple[Decimal | None, Decimal | None]:
    rules = _optional_table(document, "rules", "rules")
    if rules is None:
        return None, None
    _validate_keys(rules, frozenset({"price_drop"}), frozenset(), "rules")
    price_drop = _optional_table(rules, "price_drop", "rules.price_drop")
    if price_drop is None:
        return None, None
    _validate_keys(
        price_drop,
        frozenset({"percentage", "fixed_amount"}),
        frozenset(),
        "rules.price_drop",
    )
    percentage = _optional_decimal(
        price_drop,
        "percentage",
        "rules.price_drop.percentage",
        maximum=Decimal("100"),
    )
    amount = _optional_decimal(
        price_drop,
        "fixed_amount",
        "rules.price_drop.fixed_amount",
        maximum=None,
    )
    return percentage, amount


def _optional_decimal(
    table: Mapping[str, object],
    key: str,
    path: str,
    *,
    maximum: Decimal | None,
) -> Decimal | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise ConfigurationError(f"{path} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ConfigurationError(f"{path} must be a decimal string") from error
    if not parsed.is_finite():
        raise ConfigurationError(f"{path} must be finite")
    if parsed < Decimal("0") or (maximum is not None and parsed > maximum):
        raise ConfigurationError(f"{path} is outside its allowed range")
    return parsed


def _scheduler_interval(
    document: Mapping[str, object],
) -> timedelta | None:
    scheduler = _optional_table(document, "scheduler", "scheduler")
    if scheduler is None:
        return None
    _validate_keys(
        scheduler,
        frozenset({"interval_seconds"}),
        frozenset({"interval_seconds"}),
        "scheduler",
    )
    seconds = _positive_integer(
        scheduler["interval_seconds"],
        "scheduler.interval_seconds",
    )
    return timedelta(seconds=seconds)
