"""Resolve CLI configuration-file commands into existing command values."""

from applications.cli.arguments import (
    SyncArguments,
    SyncConfigurationArguments,
    WatchArguments,
    WatchConfigurationArguments,
)
from applications.configuration import parse_configuration
from core.configuration import ConfigurationError, ConfigurationLoader


def resolve_configured_command(
    command: SyncConfigurationArguments | WatchConfigurationArguments,
    loader: ConfigurationLoader,
) -> SyncArguments | WatchArguments:
    """Load and convert an explicit file command without changing composition."""
    if not isinstance(
        command,
        (SyncConfigurationArguments, WatchConfigurationArguments),
    ):
        raise TypeError("command must be a configuration command")
    if not callable(getattr(loader, "load", None)):
        raise TypeError("loader must expose a callable load method")

    application_config = parse_configuration(
        loader.load(command.config_file),
        command.config_file.parent,
    )
    sync = SyncArguments(
        product_urls=application_config.product_urls,
        state_file=application_config.state_file,
        timeout_seconds=application_config.timeout_seconds,
        price_drop_percentage=application_config.price_drop_percentage,
        price_drop_amount=application_config.price_drop_amount,
    )
    if isinstance(command, SyncConfigurationArguments):
        return sync
    if application_config.interval is None:
        raise ConfigurationError(
            "scheduler.interval_seconds is required for watch"
        )
    return WatchArguments(
        sync=sync,
        interval=application_config.interval,
        max_cycles=command.max_cycles,
    )
