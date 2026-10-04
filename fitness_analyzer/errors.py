"""Exception types raised by this package.

The hierarchy answers one question: can the program carry on?

``InvalidRecordError`` means one row is unusable. The loader records the
reason and moves to the next row, so a single bad line never stops a run.
``DataFileError`` and ``ReportWriteError`` mean a whole file is unusable.
Those reach the command line, which reports them and exits cleanly.
"""


class FitnessAnalyzerError(Exception):
    """Base class, so a caller can catch everything this package raises."""


class DataFileError(FitnessAnalyzerError):
    """An input file is missing, unreadable or does not have the expected columns."""


class ReportWriteError(FitnessAnalyzerError):
    """The output directory or one of the report files could not be written."""


class InvalidRecordError(ValueError, FitnessAnalyzerError):
    """One CSV row cannot be accepted.

    The error carries every problem found in the row, not only the first,
    so the rejection report can explain the row completely.
    """

    def __init__(self, problems):
        if isinstance(problems, tuple) and len(problems) == 2:
            problems = [problems]
        self.problems = list(problems)
        super().__init__("; ".join(f"{field}: {reason}"
                                   for field, reason in self.problems))


class InvalidIdentifierError(InvalidRecordError):
    """An identifier does not match its required pattern.

    This is a kind of record problem, so a caller that only cares about
    rejecting the row can catch :class:`InvalidRecordError` and handle both.
    """

    def __init__(self, field, value, pattern):
        self.value = value
        self.pattern = pattern
        super().__init__((field, f"{value!r} does not match the required format {pattern}"))
