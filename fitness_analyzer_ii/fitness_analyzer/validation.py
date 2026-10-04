"""Identifier patterns, type conversion and range checks.

Regular expressions are used for identifiers only. Numeric limits are
ordinary comparisons, because a pattern cannot tell whether 265 is a
plausible heart rate.
"""

import math
import re

from .errors import InvalidIdentifierError, InvalidRecordError

PARTICIPANT_ID_PATTERN = re.compile(r"^P\d{3}$")
SESSION_ID_PATTERN = re.compile(r"^FIT-(\d{4})-(\d{3})$")

HEART_RATE_RANGE = (35.0, 205.0)
SKIN_RESPONSE_RANGE = (0.0, 20.0)
TEMPERATURE_RANGE = (25.0, 42.0)
UNIT_RANGE = (0.0, 1.0)
MINIMUM_SIGNAL_QUALITY = 0.60


def is_number(value):
    """True for finite int and float values. Booleans are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def validate_participant_id(value):
    """Return the identifier, or raise :class:`InvalidIdentifierError`."""
    text = (value or "").strip()
    if not PARTICIPANT_ID_PATTERN.fullmatch(text):
        raise InvalidIdentifierError("participant_id", text, "P followed by three digits")
    return text


def validate_session_id(value):
    """Return the identifier, or raise :class:`InvalidIdentifierError`."""
    text = (value or "").strip()
    if not SESSION_ID_PATTERN.fullmatch(text):
        raise InvalidIdentifierError("session_id", text, "FIT-YYYY-NNN")
    return text


def session_year(session_id):
    """Return the year inside a validated session identifier.

    The same compiled pattern that validates the identifier also takes it
    apart, so the format is described in exactly one place.
    """
    match = SESSION_ID_PATTERN.fullmatch(session_id)
    if match is None:
        raise InvalidIdentifierError("session_id", session_id, "FIT-YYYY-NNN")
    return int(match.group(1))


def to_int(field, value):
    """Convert text to a whole number, or raise :class:`InvalidRecordError`."""
    text = (value or "").strip()
    if not text:
        raise InvalidRecordError((field, "is missing"))
    try:
        return int(text)
    except (TypeError, ValueError):
        raise InvalidRecordError((field, f"{text!r} is not a whole number")) from None


def to_float(field, value):
    """Convert text to a number, or raise :class:`InvalidRecordError`."""
    text = (value or "").strip()
    if not text:
        raise InvalidRecordError((field, "is missing"))
    try:
        number = float(text)
    except (TypeError, ValueError):
        raise InvalidRecordError((field, f"{text!r} is not a number")) from None
    if not math.isfinite(number):
        raise InvalidRecordError((field, f"{text!r} is not a finite number"))
    return number


def require_range(field, value, lower, upper):
    """Return the value, or raise :class:`InvalidRecordError` if out of range."""
    if not is_number(value):
        raise InvalidRecordError((field, f"{value!r} is not a number"))
    if value < lower or value > upper:
        raise InvalidRecordError(
            (field, f"{value} is outside the possible range {lower} to {upper}"))
    return value
