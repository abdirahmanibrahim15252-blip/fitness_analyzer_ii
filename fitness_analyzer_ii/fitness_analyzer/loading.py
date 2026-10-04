"""Reading the CSV files and turning rows into domain objects.

The loader has one promise: a single bad row never stops a run. Every row
it cannot accept is written down with its file, line number, field and
reason, and the loader moves on. A problem with the file itself is a
different matter, and raises :class:`DataFileError` so the command line can
report it and stop.
"""

import csv
from pathlib import Path

from .errors import DataFileError, InvalidIdentifierError, InvalidRecordError
from .models import (MEASURED_FIELDS, PROFILE_COLUMNS, SESSION_COLUMNS,
                     Observation, Participant, Session)
from .validation import (MINIMUM_SIGNAL_QUALITY, to_float, to_int,
                         validate_participant_id, validate_session_id)

FORMAT_PROBLEM = "format problem"
INVALID_VALUE = "invalid value"
UNKNOWN_PARTICIPANT = "unknown participant"
LOW_SIGNAL_QUALITY = "low signal quality"
DUPLICATE_WINDOW = "duplicate window"
MISSING_VALUE = "missing value"
UNKNOWN_SESSION = "(unreadable session id)"


class Rejection:
    """One reason why one row was not accepted."""

    def __init__(self, source, row_number, field, reason, category):
        self.source = source
        self.row_number = row_number
        self.field = field
        self.reason = reason
        self.category = category

    def describe(self):
        return (f"row {self.row_number:>3}  field {self.field:<16} "
                f"{self.category:<19} {self.reason}")

    def __repr__(self):
        return f"Rejection({self.source!r}, row {self.row_number}, {self.field!r})"


class LoadResult:
    """Everything one load produced: the sessions, and everything refused."""

    def __init__(self):
        self.sessions = {}
        self.rejections = []
        self.accepted_rows = 0
        self.total_rows = 0
        self._rejected_by_session = {}

    @property
    def rejected_rows(self):
        return self.total_rows - self.accepted_rows

    def ordered_sessions(self):
        """Sessions sorted by identifier, so every run writes the same order."""
        return [self.sessions[key] for key in sorted(self.sessions)]

    def identifiers_without_data(self):
        """Session identifiers that appeared only in rejected rows."""
        return sorted(key for key in self._rejected_by_session
                      if key not in self.sessions)

    def counts_by_category(self):
        counts = {}
        for rejection in self.rejections:
            counts[rejection.category] = counts.get(rejection.category, 0) + 1
        return dict(sorted(counts.items()))

    def note_rejected_row(self, session_key):
        self._rejected_by_session[session_key] = (
            self._rejected_by_session.get(session_key, 0) + 1)

    def finalise(self):
        """Give every session its rejected-row count.

        The count is applied once at the end rather than row by row, because
        a session is only opened when a row names both a valid session and a
        known participant. A row rejected before that point still belongs to
        the session, and this step makes sure it is counted there.
        """
        for session_id, session in self.sessions.items():
            session.set_rejected_rows(self._rejected_by_session.get(session_id, 0))
        return self


def _open_csv(path):
    """Open one CSV file, or raise :class:`DataFileError` explaining why not."""
    path = Path(path)
    try:
        return path.open(encoding="utf-8", newline="")
    except FileNotFoundError:
        raise DataFileError(f"no such file: {path}") from None
    except PermissionError:
        raise DataFileError(f"no permission to read {path}") from None
    except IsADirectoryError:
        raise DataFileError(f"{path} is a directory, not a CSV file") from None
    except OSError as error:
        raise DataFileError(f"{path} could not be opened: {error}") from None


def _read_header(reader, path, expected):
    try:
        header = next(reader)
    except StopIteration:
        raise DataFileError(f"{path} is empty") from None
    except csv.Error as error:
        raise DataFileError(f"{path} is not readable as CSV: {error}") from None
    cleaned = tuple(column.strip().lstrip("﻿") for column in header)
    if cleaned != tuple(expected):
        raise DataFileError(
            f"{path} has unexpected columns.\n  expected: {', '.join(expected)}"
            f"\n  found:    {', '.join(cleaned) or '(nothing)'}")
    return cleaned


def load_participants(path):
    """Return ``{participant_id: Participant}`` read from the profile file."""
    path = Path(path)
    participants = {}
    rejections = []
    handle = _open_csv(path)
    with handle:
        reader = csv.reader(handle)
        _read_header(reader, path, PROFILE_COLUMNS)
        try:
            rows = list(reader)
        except csv.Error as error:
            raise DataFileError(f"{path} is not readable as CSV: {error}") from None
        for row_number, row in enumerate(rows, start=2):
            if not row:
                continue
            try:
                participant = _build_participant(row)
            except InvalidRecordError as error:
                for field, reason in error.problems:
                    rejections.append(Rejection(path.name, row_number, field,
                                                reason, FORMAT_PROBLEM))
                continue
            if participant.participant_id in participants:
                rejections.append(Rejection(
                    path.name, row_number, "participant_id",
                    f"{participant.participant_id} already appeared earlier in the file",
                    FORMAT_PROBLEM))
                continue
            participants[participant.participant_id] = participant
    if not participants:
        raise DataFileError(f"{path} contained no usable participant profiles")
    return participants, rejections


def _build_participant(row):
    if len(row) != len(PROFILE_COLUMNS):
        raise InvalidRecordError(
            ("row", f"has {len(row)} fields, expected {len(PROFILE_COLUMNS)}"))
    values = dict(zip(PROFILE_COLUMNS, row))
    problems = []
    converted = {"participant_id": values["participant_id"], "name": values["name"]}
    for field in ("baseline_heart_rate", "baseline_skin_response",
                  "baseline_temperature"):
        try:
            converted[field] = to_float(field, values[field])
        except InvalidRecordError as error:
            problems.extend(error.problems)
    if problems:
        raise InvalidRecordError(problems)
    return Participant.from_row(converted)


def load_sessions(paths, participants, result=None):
    """Read one or more session files into ``result`` and return it."""
    result = result if result is not None else LoadResult()
    for path in paths:
        _load_one_session_file(Path(path), participants, result)
    return result.finalise()


def _load_one_session_file(path, participants, result):
    handle = _open_csv(path)
    with handle:
        reader = csv.reader(handle)
        _read_header(reader, path, SESSION_COLUMNS)
        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as error:
                raise DataFileError(
                    f"{path} is not readable as CSV near line "
                    f"{reader.line_num}: {error}") from None
            if not row:
                continue
            result.total_rows += 1
            _handle_row(row, reader.line_num, path.name, participants, result)


def _handle_row(row, row_number, source, participants, result):
    """Accept one row, or write down every reason it was refused."""
    inspection = _inspect_row(row, participants)
    session_key = inspection["session_key"]
    problems = inspection["problems"]

    # A session can only be opened when the identifiers are sound and the
    # participant is known. That is what lets a session whose every row was
    # refused still appear in the report, instead of vanishing quietly.
    session = result.sessions.get(session_key)
    if session is None and inspection["session_id_valid"] and inspection["participant"]:
        session = Session(session_key, inspection["participant"])
        result.sessions[session_key] = session
    if session is not None:
        session.note_source(source)

    if not problems:
        try:
            session.add_observation(_build_observation(row))
        except InvalidRecordError as error:
            problems = [(field, reason, DUPLICATE_WINDOW)
                        for field, reason in error.problems]
        else:
            result.accepted_rows += 1
            return

    for field, reason, category in problems:
        result.rejections.append(
            Rejection(source, row_number, field, reason, category))
    result.note_rejected_row(session_key)


def _inspect_row(row, participants):
    """Describe one raw row: its session key, its participant and its problems.

    Every problem in the row is collected, not only the first, so a row with
    three impossible values is explained in full rather than one field at a
    time across three runs.
    """
    problems = []
    raw_session = row[0].strip() if row else ""

    if len(row) != len(SESSION_COLUMNS):
        problems.append(("row", f"has {len(row)} fields, expected "
                                f"{len(SESSION_COLUMNS)}", FORMAT_PROBLEM))
        return {"session_key": raw_session or UNKNOWN_SESSION,
                "session_id_valid": False, "participant": None,
                "problems": problems}

    values = dict(zip(SESSION_COLUMNS, row))

    session_id_valid = True
    session_key = raw_session or UNKNOWN_SESSION
    try:
        session_key = validate_session_id(values["session_id"])
    except InvalidIdentifierError as error:
        session_id_valid = False
        problems.extend((field, reason, FORMAT_PROBLEM)
                        for field, reason in error.problems)

    participant = None
    try:
        participant_id = validate_participant_id(values["participant_id"])
    except InvalidIdentifierError as error:
        problems.extend((field, reason, FORMAT_PROBLEM)
                        for field, reason in error.problems)
    else:
        try:
            participant = participants[participant_id]
        except KeyError:
            problems.append(("participant_id",
                             f"{participant_id} is not listed in the participant file",
                             UNKNOWN_PARTICIPANT))

    problems.extend(_measurement_problems(values))
    return {"session_key": session_key, "session_id_valid": session_id_valid,
            "participant": participant, "problems": problems}


def _measurement_problems(values):
    """Every problem in the measured fields of one row."""
    problems = []
    present = {}
    for field in ("timestamp",) + MEASURED_FIELDS:
        text = (values[field] or "").strip()
        if text:
            present[field] = text
        else:
            problems.append((field, "has no value", MISSING_VALUE))

    if "timestamp" in present:
        try:
            to_int("timestamp", present["timestamp"])
        except InvalidRecordError as error:
            problems.extend((field, reason, INVALID_VALUE)
                            for field, reason in error.problems)

    numbers = {}
    for field in MEASURED_FIELDS:
        if field not in present:
            continue
        try:
            numbers[field] = to_float(field, present[field])
        except InvalidRecordError as error:
            problems.extend((name, reason, INVALID_VALUE)
                            for name, reason in error.problems)

    for field, (lower, upper) in Observation.RANGE_CHECKS:
        if field in numbers and not (lower <= numbers[field] <= upper):
            problems.append((field, f"{numbers[field]} is outside the possible "
                                    f"range {lower} to {upper}", INVALID_VALUE))

    quality = numbers.get("signal_quality")
    if (quality is not None and 0.0 <= quality <= 1.0
            and quality < MINIMUM_SIGNAL_QUALITY):
        problems.append(("signal_quality",
                         f"{quality} is below the reliability limit "
                         f"{MINIMUM_SIGNAL_QUALITY:.2f}", LOW_SIGNAL_QUALITY))
    return problems


def _build_observation(row):
    values = dict(zip(SESSION_COLUMNS, row))
    return Observation(
        to_int("timestamp", values["timestamp"]),
        to_float("heart_rate", values["heart_rate"]),
        to_float("skin_response", values["skin_response"]),
        to_float("temperature", values["temperature"]),
        to_float("activity_level", values["activity_level"]),
        to_float("signal_quality", values["signal_quality"]),
    )
