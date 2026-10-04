"""Automated tests for the Smart Fitness Session Analyzer.

Run with:  python3 tests.py

The suite covers the four cases the assignment asks for: valid data,
invalid data, a missing file, and the boundary values where a rule flips
from accept to reject. Only the standard library is used.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from fitness_analyzer import cli
from fitness_analyzer.analysis import (compare_with_baseline, describe_difference,
                                       detect_recovery, summarise)
from fitness_analyzer.analyzer import SessionAnalyzer
from fitness_analyzer.errors import (DataFileError, InvalidIdentifierError,
                                     InvalidRecordError, ReportWriteError)
from fitness_analyzer.loading import (LOW_SIGNAL_QUALITY, MISSING_VALUE,
                                      UNKNOWN_PARTICIPANT, load_participants,
                                      load_sessions)
from fitness_analyzer.models import Observation, Participant, Session
from fitness_analyzer.reporting import ensure_output_directory, format_report
from fitness_analyzer.rules import (HighActivityRule, InsufficientDataRule,
                                    RestingRule)
from fitness_analyzer.validation import (session_year, to_float, to_int,
                                         validate_participant_id,
                                         validate_session_id)

DATA = Path(__file__).resolve().parent / "data"
PROFILES = DATA / "participants.csv"
VALID_SESSIONS = DATA / "fitness_sessions.csv"
INVALID_SESSIONS = DATA / "fitness_sessions_invalid.csv"

SESSION_HEADER = ("session_id,participant_id,timestamp,heart_rate,skin_response,"
                  "temperature,activity_level,signal_quality")
PROFILE_HEADER = ("participant_id,name,baseline_heart_rate,baseline_skin_response,"
                  "baseline_temperature")
GOOD_ROW = "FIT-2026-900,P001,{t},90,2.00,32.80,0.40,0.90"


def write_csv(directory, name, header, rows):
    path = Path(directory) / name
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def official_participants():
    participants, _ = load_participants(PROFILES)
    return participants


def observation(**changes):
    values = {"timestamp": 0, "heart_rate": 90.0, "skin_response": 2.0,
              "temperature": 32.5, "activity_level": 0.4, "signal_quality": 0.9}
    values.update(changes)
    return Observation(**values)


# --------------------------------------------------------------- validation

class TestIdentifierPatterns(unittest.TestCase):
    """The two regular-expression validations."""

    def test_participant_ids(self):
        self.assertEqual(validate_participant_id(" P001 "), "P001")
        for bad in ("001", "P1", "P0012", "p001", "PABC", "", None, "P001x"):
            with self.subTest(value=bad):
                with self.assertRaises(InvalidIdentifierError):
                    validate_participant_id(bad)

    def test_session_ids(self):
        self.assertEqual(validate_session_id("FIT-2026-001"), "FIT-2026-001")
        for bad in ("FIT-26-102", "FIT-2026-1", "fit-2026-001", "REC-2026-001",
                    "FIT-2026-0010", "", None):
            with self.subTest(value=bad):
                with self.assertRaises(InvalidIdentifierError):
                    validate_session_id(bad)

    def test_identifier_error_is_a_record_error(self):
        error = InvalidIdentifierError("participant_id", "001", "P and three digits")
        self.assertIsInstance(error, InvalidRecordError)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.problems[0][0], "participant_id")

    def test_session_year_reuses_the_pattern(self):
        self.assertEqual(session_year("FIT-2026-007"), 2026)
        with self.assertRaises(InvalidIdentifierError):
            session_year("FIT-26-007")


class TestConversion(unittest.TestCase):
    def test_to_int(self):
        self.assertEqual(to_int("timestamp", " 4 "), 4)
        for bad in ("two", "", None, "4.5"):
            with self.subTest(value=bad):
                with self.assertRaises(InvalidRecordError):
                    to_int("timestamp", bad)

    def test_to_float(self):
        self.assertAlmostEqual(to_float("heart_rate", "90.5"), 90.5)
        for bad in ("fast", "", None, "nan", "inf"):
            with self.subTest(value=bad):
                with self.assertRaises(InvalidRecordError):
                    to_float("heart_rate", bad)


# ------------------------------------------------------------------- models

class TestParticipant(unittest.TestCase):
    def test_valid_participant(self):
        person = Participant("P001", "Amina Noor", 68, 1.2, 32.4)
        self.assertEqual(person.participant_id, "P001")
        self.assertEqual(person.baselines()["heart_rate"], 68)

    def test_setter_protects_the_baseline(self):
        person = Participant("P001", "Amina Noor", 68, 1.2, 32.4)
        with self.assertRaises(InvalidRecordError):
            person.baseline_heart_rate = 300
        self.assertEqual(person.baseline_heart_rate, 68)

    def test_identifier_is_read_only(self):
        person = Participant("P001", "Amina Noor", 68, 1.2, 32.4)
        with self.assertRaises(AttributeError):
            person.participant_id = "P999"

    def test_identifier_and_name_are_validated(self):
        with self.assertRaises(InvalidIdentifierError):
            Participant("001", "Amina Noor", 68, 1.2, 32.4)
        with self.assertRaises(InvalidRecordError):
            Participant("P001", "   ", 68, 1.2, 32.4)


class TestObservation(unittest.TestCase):
    def test_valid_window(self):
        self.assertEqual(observation().heart_rate, 90.0)

    def test_impossible_values_are_refused(self):
        for change in (dict(heart_rate=265.0), dict(heart_rate=-15.0),
                       dict(skin_response=-0.5), dict(temperature=55.0),
                       dict(activity_level=1.3), dict(signal_quality=1.4),
                       dict(timestamp=-1), dict(timestamp=1.5), dict(timestamp=True)):
            with self.subTest(change=change):
                with self.assertRaises((InvalidRecordError, TypeError)):
                    observation(**change)


class TestSession(unittest.TestCase):
    def setUp(self):
        self.person = Participant("P001", "Amina Noor", 68, 1.2, 32.4)

    def test_composition_and_ordering(self):
        session = Session("FIT-2026-001", self.person)
        session.add_observation(observation(timestamp=1))
        session.add_observation(observation(timestamp=0))
        self.assertEqual([item.timestamp for item in session.observations], [0, 1])
        self.assertEqual(len(session), 2)

    def test_duplicate_timestamp_is_refused(self):
        session = Session("FIT-2026-001", self.person)
        session.add_observation(observation(timestamp=0))
        with self.assertRaises(InvalidRecordError):
            session.add_observation(observation(timestamp=0))

    def test_observations_are_handed_out_as_a_tuple(self):
        session = Session("FIT-2026-001", self.person)
        self.assertIsInstance(session.observations, tuple)
        with self.assertRaises(TypeError):
            session.add_observation({"timestamp": 0})

    def test_session_needs_a_participant_and_a_valid_identifier(self):
        with self.assertRaises(TypeError):
            Session("FIT-2026-001", "P001")
        with self.assertRaises(InvalidIdentifierError):
            Session("FIT-26-1", self.person)


# ----------------------------------------------------------------- analysis

class TestAnalysisFunctions(unittest.TestCase):
    def test_summarise(self):
        self.assertEqual(summarise([1, 2, 3]),
                         {"count": 3, "average": 2, "minimum": 1, "maximum": 3})
        self.assertIsNone(summarise([])["average"])

    def test_compare_with_baseline(self):
        comparison = compare_with_baseline(80, 64)
        self.assertEqual(comparison["difference"], 16)
        self.assertEqual(comparison["percent_change"], 25.0)

    def test_describe_difference(self):
        self.assertEqual(describe_difference(12.34, " bpm"), "12.3 bpm above baseline")
        self.assertEqual(describe_difference(-2, " bpm"), "2.0 bpm below baseline")
        self.assertEqual(describe_difference(0.01), "level with baseline")
        self.assertEqual(describe_difference(None), "not available")

    def test_recovery_after_a_warm_up(self):
        """The case Assignment I's first-third rule could not see."""
        heart_rates = [72, 138, 151, 132, 104, 82]
        activity = [0.20, 0.86, 0.92, 0.70, 0.42, 0.18]
        result = detect_recovery(heart_rates, activity, 68)
        self.assertTrue(result["detected"])
        self.assertEqual(result["peak_heart_rate"], 151)
        first_third = sum(heart_rates[:2]) / 2
        last_third = sum(heart_rates[-2:]) / 2
        self.assertLess(first_third - last_third, 15,
                        "the old first-third rule would have missed this session")

    def test_no_recovery_when_effort_continues(self):
        result = detect_recovery([72, 112, 148, 162, 155, 146],
                                 [0.25, 0.66, 0.88, 0.94, 0.91, 0.84], 63)
        self.assertFalse(result["detected"])

    def test_no_recovery_without_real_effort(self):
        result = detect_recovery([68, 69, 70, 69, 68, 69],
                                 [0.08, 0.10, 0.12, 0.09, 0.07, 0.10], 68)
        self.assertFalse(result["detected"])

    def test_too_few_windows(self):
        self.assertFalse(detect_recovery([130, 80], [0.8, 0.1], 68)["detected"])

    def test_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            detect_recovery([100, 90], [0.5], 68)


class TestRules(unittest.TestCase):
    FACTS = {"total_windows": 6, "usable_windows": 6, "usable_ratio": 1.0,
             "heart_rate_elevation": 50.0, "average_activity": 0.5,
             "recovery": {"detected": False}}

    def test_overridden_matches(self):
        self.assertTrue(HighActivityRule().matches(self.FACTS))
        self.assertFalse(InsufficientDataRule().matches(self.FACTS))
        self.assertTrue(RestingRule().matches(self.FACTS))

    def test_evaluate_returns_label_and_explanation(self):
        verdict = HighActivityRule().evaluate(self.FACTS)
        self.assertEqual(verdict["label"], "high activity")
        self.assertIn("heart rate", verdict["explanation"])

    def test_analyzer_needs_rules(self):
        with self.assertRaises(ValueError):
            SessionAnalyzer([])


# ------------------------------------------------------- loading valid data

class TestLoadingOfficialFiles(unittest.TestCase):
    def setUp(self):
        self.participants = official_participants()

    def test_profiles(self):
        self.assertEqual(sorted(self.participants), ["P001", "P002", "P003"])
        self.assertEqual(self.participants["P001"].name, "Amina Noor")
        self.assertEqual(self.participants["P002"].baseline_heart_rate, 74)

    def test_valid_file_only(self):
        result = load_sessions([VALID_SESSIONS], self.participants)
        self.assertEqual(result.total_rows, 29)
        self.assertEqual(result.accepted_rows, 24)
        self.assertEqual(result.rejected_rows, 5)
        self.assertEqual(sorted(result.sessions), [
            "FIT-2026-001", "FIT-2026-002", "FIT-2026-003",
            "FIT-2026-004", "FIT-2026-005"])
        self.assertTrue(all(item.category == LOW_SIGNAL_QUALITY
                            for item in result.rejections))

    def test_both_files(self):
        result = load_sessions([VALID_SESSIONS, INVALID_SESSIONS], self.participants)
        self.assertEqual(result.accepted_rows, 25)
        self.assertEqual(result.rejected_rows, 15)
        self.assertEqual(result.identifiers_without_data(),
                         ["FIT-2026-103", "FIT-26-102"])

    def test_every_rejection_names_file_row_field_and_reason(self):
        result = load_sessions([INVALID_SESSIONS], self.participants)
        for rejection in result.rejections:
            self.assertEqual(rejection.source, "fitness_sessions_invalid.csv")
            self.assertGreaterEqual(rejection.row_number, 2)
            self.assertTrue(rejection.field)
            self.assertTrue(rejection.reason)

    def test_each_kind_of_invalid_row_is_caught(self):
        result = load_sessions([INVALID_SESSIONS], self.participants)
        found = {(item.row_number, item.field) for item in result.rejections}
        expected = {
            (3, "heart_rate"),       # text where a number belongs
            (4, "participant_id"),   # identifier pattern
            (5, "activity_level"),   # missing value
            (6, "signal_quality"),   # out of range
            (7, "session_id"),       # identifier pattern
            (8, "participant_id"),   # unknown participant
            (9, "timestamp"),        # not a whole number
            (10, "heart_rate"),      # impossible value
            (11, "skin_response"),   # three problems in one row
            (11, "temperature"),
            (11, "activity_level"),
            (12, "row"),             # unexpected row length
        }
        self.assertTrue(expected <= found, expected - found)
        self.assertEqual(result.accepted_rows, 1)

    def test_categories(self):
        result = load_sessions([VALID_SESSIONS, INVALID_SESSIONS], self.participants)
        counts = result.counts_by_category()
        self.assertEqual(counts[LOW_SIGNAL_QUALITY], 5)
        self.assertEqual(counts[UNKNOWN_PARTICIPANT], 1)
        self.assertEqual(counts[MISSING_VALUE], 1)


# ----------------------------------------------------- missing and bad files

class TestFileProblems(unittest.TestCase):
    def setUp(self):
        self.participants = official_participants()

    def test_missing_profile_file(self):
        with self.assertRaises(DataFileError) as caught:
            load_participants(DATA / "does_not_exist.csv")
        self.assertIn("no such file", str(caught.exception))

    def test_missing_session_file(self):
        with self.assertRaises(DataFileError):
            load_sessions([DATA / "missing.csv"], self.participants)

    def test_directory_instead_of_file(self):
        with self.assertRaises(DataFileError):
            load_participants(DATA)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(DataFileError) as caught:
                load_sessions([path], self.participants)
            self.assertIn("empty", str(caught.exception))

    def test_wrong_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, "odd.csv", "a,b,c", ["1,2,3"])
            with self.assertRaises(DataFileError) as caught:
                load_sessions([path], self.participants)
            self.assertIn("unexpected columns", str(caught.exception))

    def test_header_only_file_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, "head.csv", SESSION_HEADER, [])
            result = load_sessions([path], self.participants)
            self.assertEqual(result.total_rows, 0)
            self.assertEqual(result.sessions, {})

    def test_profile_file_without_usable_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, "p.csv", PROFILE_HEADER,
                             ["XXX,No One,68,1.2,32.4"])
            with self.assertRaises(DataFileError):
                load_participants(path)

    def test_output_path_that_is_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            blocker = Path(folder) / "output"
            blocker.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(ReportWriteError):
                ensure_output_directory(blocker)


# --------------------------------------------------------- boundary values

class TestBoundaries(unittest.TestCase):
    """Exactly on the limit is accepted. One step past it is not."""

    def setUp(self):
        self.participants = official_participants()

    def load_row(self, row):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, "b.csv", SESSION_HEADER, [row])
            return load_sessions([path], self.participants)

    def assert_accepted(self, row):
        self.assertEqual(self.load_row(row).accepted_rows, 1, row)

    def assert_rejected(self, row):
        self.assertEqual(self.load_row(row).accepted_rows, 0, row)

    def test_signal_quality_limit(self):
        self.assert_accepted("FIT-2026-900,P001,0,90,2.0,32.8,0.4,0.60")
        self.assert_rejected("FIT-2026-900,P001,0,90,2.0,32.8,0.4,0.59")

    def test_heart_rate_limits(self):
        self.assert_accepted("FIT-2026-900,P001,0,35,2.0,32.8,0.4,0.9")
        self.assert_accepted("FIT-2026-900,P001,0,205,2.0,32.8,0.4,0.9")
        self.assert_rejected("FIT-2026-900,P001,0,34.9,2.0,32.8,0.4,0.9")
        self.assert_rejected("FIT-2026-900,P001,0,205.1,2.0,32.8,0.4,0.9")

    def test_activity_limits(self):
        self.assert_accepted("FIT-2026-900,P001,0,90,2.0,32.8,0.0,0.9")
        self.assert_accepted("FIT-2026-900,P001,0,90,2.0,32.8,1.0,0.9")
        self.assert_rejected("FIT-2026-900,P001,0,90,2.0,32.8,1.01,0.9")

    def test_timestamp_limits(self):
        self.assert_accepted("FIT-2026-900,P001,0,90,2.0,32.8,0.4,0.9")
        self.assert_rejected("FIT-2026-900,P001,-1,90,2.0,32.8,0.4,0.9")

    def test_too_many_fields(self):
        self.assert_rejected("FIT-2026-900,P001,0,90,2.0,32.8,0.4,0.9,extra")

    def test_duplicate_window_in_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, "dup.csv", SESSION_HEADER,
                             [GOOD_ROW.format(t=0), GOOD_ROW.format(t=0)])
            result = load_sessions([path], self.participants)
            self.assertEqual(result.accepted_rows, 1)
            self.assertEqual(result.rejected_rows, 1)
            self.assertIn("duplicates", result.rejections[0].reason)

    def test_minimum_usable_windows(self):
        analyzer = SessionAnalyzer.with_default_rules()
        with tempfile.TemporaryDirectory() as folder:
            three = write_csv(folder, "three.csv", SESSION_HEADER,
                              [GOOD_ROW.format(t=index) for index in range(3)])
            four = write_csv(folder, "four.csv", SESSION_HEADER,
                             [GOOD_ROW.format(t=index) for index in range(4)])
            # Three usable rows is below the floor. Four is enough for a verdict,
            # and these rows sit above the moderate limits for P001.
            for path, expected in ((three, "insufficient data"),
                                   (four, "moderate activity")):
                result = load_sessions([path], self.participants)
                verdict = analyzer.analyze(result.ordered_sessions()[0])
                with self.subTest(path=path.name):
                    self.assertEqual(verdict["classification"], expected)


# -------------------------------------------------------- end to end results

class TestAnalysisOfOfficialData(unittest.TestCase):
    EXPECTED = {
        "FIT-2026-001": "resting",
        "FIT-2026-002": "moderate activity",
        "FIT-2026-003": "high activity",
        "FIT-2026-004": "recovering",
        "FIT-2026-005": "insufficient data",
        "FIT-2026-101": "insufficient data",
        "FIT-2026-102": "insufficient data",
    }

    def setUp(self):
        participants = official_participants()
        result = load_sessions([VALID_SESSIONS, INVALID_SESSIONS], participants)
        analyzer = SessionAnalyzer.with_default_rules()
        self.results = {item["session_id"]: item
                        for item in map(analyzer.analyze, result.ordered_sessions())}

    def test_every_session_is_classified_as_expected(self):
        self.assertEqual({key: value["classification"]
                          for key, value in self.results.items()}, self.EXPECTED)

    def test_all_five_categories_appear(self):
        self.assertEqual(len({value["classification"]
                              for value in self.results.values()}), 5)

    def test_result_is_a_structured_dictionary(self):
        result = self.results["FIT-2026-004"]
        for key in ("session_id", "session_year", "participant_id",
                    "participant_name", "classification", "explanation",
                    "windows", "summaries", "comparison", "recovery", "sources"):
            self.assertIn(key, result)
        self.assertEqual(result["session_year"], 2026)
        self.assertEqual(result["windows"]["usable"], 6)
        self.assertTrue(result["recovery"]["detected"])

    def test_low_quality_session_has_no_averages(self):
        result = self.results["FIT-2026-005"]
        self.assertEqual(result["windows"]["usable"], 0)
        self.assertIsNone(result["summaries"]["heart_rate"]["average"])

    def test_report_text_mentions_the_verdict(self):
        self.assertIn("RECOVERING", format_report(self.results["FIT-2026-004"]))


# ------------------------------------------------------------ output files

class TestOutputFiles(unittest.TestCase):
    def test_files_are_created_in_a_new_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new" / "output"
            with redirect_stdout(io.StringIO()):
                summary = cli.run(PROFILES, [VALID_SESSIONS, INVALID_SESSIONS], output)
            for name in ("analysis_summary.csv", "analysis_report.txt",
                         "rejected_records.txt"):
                self.assertTrue((output / name).is_file(), name)
            self.assertEqual(summary["accepted_rows"], 25)
            self.assertEqual(summary["rejected_rows"], 15)
            self.assertEqual(summary["sessions"], 7)

    def test_running_twice_produces_identical_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            with redirect_stdout(io.StringIO()):
                cli.run(PROFILES, [VALID_SESSIONS, INVALID_SESSIONS], output)
                first = {path.name: path.read_bytes()
                         for path in sorted(output.iterdir())}
                cli.run(PROFILES, [VALID_SESSIONS, INVALID_SESSIONS], output)
                second = {path.name: path.read_bytes()
                          for path in sorted(output.iterdir())}
            self.assertEqual(first, second)

    def test_summary_csv_has_one_row_per_session(self):
        import csv
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            with redirect_stdout(io.StringIO()):
                cli.run(PROFILES, [VALID_SESSIONS, INVALID_SESSIONS], output)
            with (output / "analysis_summary.csv").open(encoding="utf-8",
                                                        newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["session_id"], "FIT-2026-001")
        self.assertEqual(rows[3]["recovery_detected"], "yes")

    def test_rejected_file_names_file_row_and_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            with redirect_stdout(io.StringIO()):
                cli.run(PROFILES, [VALID_SESSIONS, INVALID_SESSIONS], output)
            text = (output / "rejected_records.txt").read_text(encoding="utf-8")
        self.assertIn("fitness_sessions_invalid.csv", text)
        self.assertIn("row  11", text)
        self.assertIn("is not listed in the participant file", text)
        self.assertIn("accepted rows", text)


# -------------------------------------------------------------- command line

class TestCommandLine(unittest.TestCase):
    def test_successful_run(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = ["--profiles", str(PROFILES),
                         "--sessions", str(VALID_SESSIONS), str(INVALID_SESSIONS),
                         "--output", str(Path(folder) / "output")]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(arguments), 0)
            self.assertIn("COMPLETED", output.getvalue())
            self.assertIn("rows accepted", output.getvalue())

    def test_defaults_run_without_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["--output", str(Path(folder) / "out")]), 0)

    def test_missing_file_exits_with_one(self):
        with tempfile.TemporaryDirectory() as folder:
            arguments = ["--profiles", str(DATA / "nope.csv"),
                         "--output", str(Path(folder) / "output")]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(arguments), 1)

    def test_quiet_prints_only_the_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            with redirect_stdout(io.StringIO()) as output:
                cli.main(["--quiet", "--output", str(Path(folder) / "out")])
            self.assertNotIn("OVERVIEW", output.getvalue())
            self.assertIn("COMPLETED", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
