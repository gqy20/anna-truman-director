"""Custom exceptions with JSON-RPC error code mapping.

Business error codes under the ``TrumanError`` umbrella:
    -32000  framework fallback (bare ``Exception`` in the protocol layer)
    -32001  WorldNotInitializedError
    -32002  InvalidWorldSpecError
    -32003  UnknownScenarioError
    -32004  TickBudgetExceededError
"""


class TrumanError(Exception):
    """Base exception for all Truman Director errors."""

    code: int = -32000


class WorldNotInitializedError(TrumanError):
    """Called tick / inject_event before init."""

    code = -32001


class InvalidWorldSpecError(TrumanError):
    """A custom world spec failed validation (missing field, bad reference, bad type, etc.)."""

    code = -32002


class UnknownScenarioError(TrumanError):
    """Scenario slug not in SCENARIOS dict."""

    code = -32003


class TickBudgetExceededError(TrumanError):
    """A ``tick`` asked for more ticks than the per-invoke sampling budget allows.

    Each invoke gets ``max_calls`` (default 8) sampling calls from the host, and one tick
    consumes exactly one. Driving more ticks than that must happen from the bundle as a
    loop of single-tick invokes — a single big invoke would burn the budget, persist the
    first handful of ticks, then fail partway through, leaving a half-applied world.
    """

    code = -32004
