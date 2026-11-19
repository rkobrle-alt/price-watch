"""Home Assistant Infrastructure exception contract."""


class HomeAssistantError(RuntimeError):
    """Report an operational Home Assistant communication failure."""


class HomeAssistantRequestRejectedError(HomeAssistantError):
    """Report a request known to fail before service execution."""
