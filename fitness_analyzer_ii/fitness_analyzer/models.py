"""The domain objects: the person, one measurement window, and the session.

A rule carried over from Assignment I: an object refuses to exist in an
impossible state. The loader explains problems to the reader; these classes
enforce the invariant, so a Session built anywhere in the program, including
in a test, can only contain trustworthy measurements.
"""

from .errors import InvalidRecordError
from .validation import (HEART_RATE_RANGE, SKIN_RESPONSE_RANGE,
                         TEMPERATURE_RANGE, UNIT_RANGE, require_range,
                         validate_participant_id, validate_session_id)

PROFILE_COLUMNS = ("participant_id", "name", "baseline_heart_rate",
                   "baseline_skin_response", "baseline_temperature")
SESSION_COLUMNS = ("session_id", "participant_id", "timestamp", "heart_rate",
                   "skin_response", "temperature", "activity_level",
                   "signal_quality")
MEASURED_FIELDS = ("heart_rate", "skin_response", "temperature",
                   "activity_level", "signal_quality")


class Participant:
    """A person, with the personal reference values their results are judged against.

    The baselines live in protected attributes. They can only be replaced
    through property setters that validate the new value, so a participant
    with a resting heart rate of 300 bpm cannot exist inside the program.
    """

    def __init__(self, participant_id, name, baseline_heart_rate,
                 baseline_skin_response, baseline_temperature):
        self._participant_id = validate_participant_id(participant_id)
        text = (name or "").strip()
        if not text:
            raise InvalidRecordError(("name", "is missing"))
        self._name = text
        self.baseline_heart_rate = baseline_heart_rate
        self.baseline_skin_response = baseline_skin_response
        self.baseline_temperature = baseline_temperature

    @classmethod
    def from_row(cls, row):
        """Alternative constructor for one already converted profile row."""
        missing = [column for column in PROFILE_COLUMNS if column not in row]
        if missing:
            raise InvalidRecordError([(column, "is missing") for column in missing])
        return cls(*(row[column] for column in PROFILE_COLUMNS))

    @property
    def participant_id(self):
        return self._participant_id

    @property
    def name(self):
        return self._name

    @property
    def baseline_heart_rate(self):
        return self._baseline_heart_rate

    @baseline_heart_rate.setter
    def baseline_heart_rate(self, value):
        self._baseline_heart_rate = require_range("baseline_heart_rate", value, 30.0, 120.0)

    @property
    def baseline_skin_response(self):
        return self._baseline_skin_response

    @baseline_skin_response.setter
    def baseline_skin_response(self, value):
        self._baseline_skin_response = require_range(
            "baseline_skin_response", value, *SKIN_RESPONSE_RANGE)

    @property
    def baseline_temperature(self):
        return self._baseline_temperature

    @baseline_temperature.setter
    def baseline_temperature(self, value):
        self._baseline_temperature = require_range(
            "baseline_temperature", value, *TEMPERATURE_RANGE)

    def baselines(self):
        """The baselines keyed by the measurement field each one describes."""
        return {
            "heart_rate": self.baseline_heart_rate,
            "skin_response": self.baseline_skin_response,
            "temperature": self.baseline_temperature,
        }

    def __repr__(self):
        return f"Participant({self.participant_id!r}, {self.name!r})"


class Observation:
    """One measurement window that has already passed validation."""

    RANGE_CHECKS = (
        ("heart_rate", HEART_RATE_RANGE),
        ("skin_response", SKIN_RESPONSE_RANGE),
        ("temperature", TEMPERATURE_RANGE),
        ("activity_level", UNIT_RANGE),
        ("signal_quality", UNIT_RANGE),
    )

    def __init__(self, timestamp, heart_rate, skin_response, temperature,
                 activity_level, signal_quality):
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
            raise InvalidRecordError(
                ("timestamp", f"{timestamp!r} is not a whole number of 0 or more"))
        self._timestamp = timestamp
        values = {
            "heart_rate": heart_rate,
            "skin_response": skin_response,
            "temperature": temperature,
            "activity_level": activity_level,
            "signal_quality": signal_quality,
        }
        for field, (lower, upper) in self.RANGE_CHECKS:
            require_range(field, values[field], lower, upper)
        self._heart_rate = values["heart_rate"]
        self._skin_response = values["skin_response"]
        self._temperature = values["temperature"]
        self._activity_level = values["activity_level"]
        self._signal_quality = values["signal_quality"]

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def heart_rate(self):
        return self._heart_rate

    @property
    def skin_response(self):
        return self._skin_response

    @property
    def temperature(self):
        return self._temperature

    @property
    def activity_level(self):
        return self._activity_level

    @property
    def signal_quality(self):
        return self._signal_quality

    def value(self, field):
        return getattr(self, field)

    def __repr__(self):
        return f"Observation(timestamp={self.timestamp}, heart_rate={self.heart_rate})"


class Session:
    """One training session: a participant composed with its measurement windows.

    The session owns its observations and hands them out only as a tuple, so
    windows enter through :meth:`add_observation` and nowhere else. It also
    counts the rows the loader had to reject, which is what lets the analysis
    say how much of the session survived validation.
    """

    def __init__(self, session_id, participant):
        if not isinstance(participant, Participant):
            raise TypeError("participant must be a Participant")
        self._session_id = validate_session_id(session_id)
        self._participant = participant
        self._observations = []
        self._rejected_rows = 0
        self._sources = []

    @property
    def session_id(self):
        return self._session_id

    @property
    def participant(self):
        return self._participant

    @property
    def observations(self):
        return tuple(sorted(self._observations, key=lambda item: item.timestamp))

    @property
    def rejected_rows(self):
        return self._rejected_rows

    @property
    def total_rows(self):
        return len(self._observations) + self._rejected_rows

    @property
    def sources(self):
        return tuple(self._sources)

    def add_observation(self, observation):
        """Add one window, or raise :class:`InvalidRecordError` on a duplicate."""
        if not isinstance(observation, Observation):
            raise TypeError("only Observation objects can be added")
        if any(existing.timestamp == observation.timestamp
               for existing in self._observations):
            raise InvalidRecordError(
                ("timestamp", f"{observation.timestamp} duplicates an earlier window "
                              f"in session {self._session_id}"))
        self._observations.append(observation)

    def set_rejected_rows(self, count):
        """Record how many rows of this session the loader had to reject."""
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("count must be a whole number of 0 or more")
        self._rejected_rows = count

    def note_source(self, filename):
        if filename not in self._sources:
            self._sources.append(filename)

    def values(self, field):
        """The values of one field, in time order."""
        return [observation.value(field) for observation in self.observations]

    def __len__(self):
        return len(self._observations)
