"""Command line handling, and the completion summary printed at the end."""

import argparse
import sys
from pathlib import Path

from .analyzer import SessionAnalyzer
from .errors import DataFileError, ReportWriteError
from .loading import load_participants, load_sessions
from .reporting import (ensure_output_directory, format_overview,
                        write_rejected_txt, write_report_txt, write_summary_csv)

PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DEFAULT_DATA = REPOSITORY_ROOT / "data"
DEFAULT_PROFILES = DEFAULT_DATA / "participants.csv"
DEFAULT_SESSIONS = (DEFAULT_DATA / "fitness_sessions.csv",
                    DEFAULT_DATA / "fitness_sessions_invalid.csv")
DEFAULT_OUTPUT = Path("output")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Analyse wearable fitness sessions stored in CSV files.")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES,
                        help="participant profile CSV "
                             "(default: data/participants.csv)")
    parser.add_argument("--sessions", type=Path, nargs="+",
                        default=list(DEFAULT_SESSIONS),
                        help="one or more session CSV files (default: the valid "
                             "and the invalid official files)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="directory for the report files (default: output)")
    parser.add_argument("--quiet", action="store_true",
                        help="print only the completion summary")
    return parser


def run(profiles_path, session_paths, output_path, quiet=False, stream=None):
    """Load, analyse, write the reports and return the completion summary."""
    stream = stream if stream is not None else sys.stdout

    participants, profile_rejections = load_participants(profiles_path)
    load_result = load_sessions(session_paths, participants)
    load_result.rejections[:0] = profile_rejections

    analyzer = SessionAnalyzer.with_default_rules()
    results = [analyzer.analyze(session) for session in load_result.ordered_sessions()]

    directory = ensure_output_directory(output_path)
    written = [
        write_summary_csv(directory / "analysis_summary.csv", results),
        write_report_txt(directory / "analysis_report.txt", results, load_result),
        write_rejected_txt(directory / "rejected_records.txt", load_result),
    ]

    if not quiet and results:
        print(format_overview(results), file=stream)
        print(file=stream)

    summary = {
        "participants": len(participants),
        "sessions": len(results),
        "accepted_rows": load_result.accepted_rows,
        "rejected_rows": load_result.rejected_rows,
        "total_rows": load_result.total_rows,
        "files": [str(path) for path in written],
        "identifiers_without_data": load_result.identifiers_without_data(),
    }
    print(_completion_summary(summary), file=stream)
    return summary


def _completion_summary(summary):
    lines = [
        " COMPLETED",
        f"   participants loaded : {summary['participants']}",
        f"   sessions analysed   : {summary['sessions']}",
        f"   rows accepted       : {summary['accepted_rows']}",
        f"   rows rejected       : {summary['rejected_rows']}",
        "   files written       : " + ", ".join(summary["files"]),
    ]
    if summary["identifiers_without_data"]:
        lines.append("   no usable rows for  : "
                     + ", ".join(summary["identifiers_without_data"]))
    return "\n".join(lines)


def main(argv=None):
    """Entry point. Returns the exit status: 0 on success, 1 on a file problem."""
    arguments = build_parser().parse_args(argv)
    try:
        run(arguments.profiles, arguments.sessions, arguments.output,
            quiet=arguments.quiet)
    except DataFileError as error:
        print(f"Cannot read the input data: {error}", file=sys.stderr)
        return 1
    except ReportWriteError as error:
        print(f"Cannot write the reports: {error}", file=sys.stderr)
        return 1
    return 0
