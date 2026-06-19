"""Custom exceptions with JSON-RPC error code mapping."""


class TrumanError(Exception):
    """Base exception for all Truman Director errors."""

    code: int = -32000


class WorldNotInitializedError(TrumanError):
    """Called tick / inject_event before init."""

    code = -32001


class UnknownScenarioError(TrumanError):
    """Scenario slug not in SCENARIOS dict."""

    code = -32003
