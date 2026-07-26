"""Application errors."""


class IntervalsError(RuntimeError):
    """Base error for Intervals.icu operations."""


class IntervalsAPIError(IntervalsError):
    """The Intervals.icu API returned an error."""


class SafetyViolation(IntervalsError):
    """A requested mutation crossed the managed-draft boundary."""


class ConcurrentModification(IntervalsError):
    """A remote draft changed since the caller last read it."""
