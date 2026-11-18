"""Domain exceptions. Platform errors are translated into these."""


class GpuccError(Exception):
    """Base class for all expected application errors."""


class PlatformApiError(GpuccError):
    """A Windows or vendor API call failed."""

    def __init__(self, api: str, code: int, detail: str = "") -> None:
        self.api = api
        self.code = code
        super().__init__(f"{api} failed (0x{code & 0xFFFFFFFF:08X}){': ' + detail if detail else ''}")


class SourceUnavailableError(GpuccError):
    """A telemetry source's library/driver is not present."""
