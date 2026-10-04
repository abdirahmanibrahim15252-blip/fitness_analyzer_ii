"""Turning results into text, and writing the three output files.

Nothing written here contains a clock time or a run number. Two runs over
the same input produce byte for byte identical files, which is what makes
re-running the program safe and its output predictable.
"""

import csv
import textwrap
from pathlib import Path

from .analysis import describe_difference
from .errors import ReportWriteError

LINE_WIDTH = 78
FIELD_LABELS = {
    "heart_rate": ("Heart rate", " bpm", 1),
    "skin_response": ("Skin response", " units", 2),
    "temperature": ("Temperature", " C", 2),
    "activity_level": ("Activity", "", 2),
    "signal_quality": ("Signal quality", "", 2),
}
SUMMARY_COLUMNS = (
    "session_id", "participant_id", "participant_name", "classification",
    "total_rows", "usable_rows", "rejected_rows", "usable_percent",
    "average_heart_rate", "heart_rate_vs_baseline", "average_skin_response",
    "skin_response_vs_baseline", "average_temperature",
    "temperature_vs_baseline", "average_activity", "average_signal_quality",
    "recovery_detected", "explanation",
)


def format_number(value, digits=1):
    return "" if value is None else f"{value:.{digits}f}"


def _wrapped(prefix, text):
    indent = " " * len(prefix)
    return textwrap.wrap(text, width=LINE_WIDTH, initial_indent=prefix,
                         subsequent_indent=indent)


def format_report(result):
    """The readable report for one analysed session."""
    rule = "=" * LINE_WIDTH
    lines = [rule,
             f" SESSION {result['session_id']} · {result['participant_name']} "
             f"({result['participant_id']})",
             rule]
    lines += _wrapped(" Verdict   ", result["classification"].upper())
    lines += _wrapped(" Why       ", result["explanation"])

    windows = result["windows"]
    lines += ["", f" Data quality: {windows['usable']} of {windows['total']} rows "
                  f"usable ({windows['usable_percent']}%), "
                  f"source {', '.join(result['sources']) or 'unknown'}"]

    lines += ["", f" {'Measurement':<16}{'Average':>9}{'Min':>9}{'Max':>9}"
                  f"   Compared with personal baseline",
              " " + "-" * (LINE_WIDTH - 1)]
    for field, (name, unit, digits) in FIELD_LABELS.items():
        summary = result["summaries"][field]
        if field in result["comparison"]:
            note = describe_difference(result["comparison"][field]["difference"],
                                       unit, digits)
        else:
            note = "no personal baseline"
        average = format_number(summary["average"], digits) or "n/a"
        minimum = format_number(summary["minimum"], digits) or "n/a"
        maximum = format_number(summary["maximum"], digits) or "n/a"
        lines.append(f" {name:<16}{average:>9}{minimum:>9}{maximum:>9}   {note}")

    recovery = result["recovery"]
    lines.append("")
    if recovery["peak_heart_rate"] is None:
        lines.append(" Recovery check: not enough usable rows to look for a cool down.")
    else:
        status = "recovery detected" if recovery["detected"] else "no cool down"
        lines += _wrapped(" Recovery check: ",
                          f"peak {recovery['peak_heart_rate']:.0f} bpm "
                          f"({recovery['peak_elevation']:.0f} above baseline), ending at "
                          f"{recovery['final_heart_rate']:.0f} bpm, activity "
                          f"{recovery['peak_activity']:.2f} to "
                          f"{recovery['final_activity']:.2f}: {status}.")
    lines.append(rule)
    return "\n".join(lines)


def format_overview(results):
    """One table listing every analysed session."""
    lines = [" OVERVIEW", " " + "=" * 64,
             f" {'Session':<16}{'Participant':<14}{'Rows':<10}{'Verdict'}",
             " " + "-" * 64]
    for result in results:
        windows = result["windows"]
        rows = f"{windows['usable']}/{windows['total']}"
        lines.append(f" {result['session_id']:<16}{result['participant_id']:<14}"
                     f"{rows:<10}{result['classification']}")
    return "\n".join(lines)


def ensure_output_directory(path):
    """Create the output directory when it does not exist."""
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ReportWriteError(f"no permission to create {path}") from None
    except OSError as error:
        raise ReportWriteError(f"{path} could not be created: {error}") from None
    if not path.is_dir():
        raise ReportWriteError(f"{path} exists but is not a directory")
    return path


def _open_for_writing(path):
    try:
        return Path(path).open("w", encoding="utf-8", newline="")
    except PermissionError:
        raise ReportWriteError(f"no permission to write {path}") from None
    except OSError as error:
        raise ReportWriteError(f"{path} could not be written: {error}") from None


def write_summary_csv(path, results):
    """One row per analysed session."""
    handle = _open_for_writing(path)
    with handle:
        writer = csv.writer(handle)
        writer.writerow(SUMMARY_COLUMNS)
        for result in results:
            summaries = result["summaries"]
            comparison = result["comparison"]
            windows = result["windows"]
            writer.writerow([
                result["session_id"], result["participant_id"],
                result["participant_name"], result["classification"],
                windows["total"], windows["usable"], windows["rejected"],
                windows["usable_percent"],
                format_number(summaries["heart_rate"]["average"], 1),
                format_number(comparison["heart_rate"]["difference"], 1),
                format_number(summaries["skin_response"]["average"], 2),
                format_number(comparison["skin_response"]["difference"], 2),
                format_number(summaries["temperature"]["average"], 2),
                format_number(comparison["temperature"]["difference"], 2),
                format_number(summaries["activity_level"]["average"], 2),
                format_number(summaries["signal_quality"]["average"], 2),
                "yes" if result["recovery"]["detected"] else "no",
                result["explanation"],
            ])
    return Path(path)


def write_report_txt(path, results, load_result):
    """The readable explanation of every result."""
    handle = _open_for_writing(path)
    with handle:
        handle.write("SMART FITNESS SESSION ANALYZER\n")
        handle.write("Analysis report\n\n")
        for result in results:
            handle.write(format_report(result))
            handle.write("\n\n")
        handle.write(format_overview(results))
        handle.write("\n")
        missing = load_result.identifiers_without_data()
        if missing:
            handle.write("\n Session identifiers that produced no usable rows:\n")
            for identifier in missing:
                handle.write(f"   {identifier}\n")
            handle.write(" See rejected_records.txt for the reasons.\n")
    return Path(path)


def write_rejected_txt(path, load_result):
    """Every refused row, with its file, line number, field and reason."""
    handle = _open_for_writing(path)
    with handle:
        handle.write("REJECTED RECORDS\n")
        handle.write("Line numbers refer to the physical line in the named file, "
                     "where line 1 is the header.\n\n")
        if not load_result.rejections:
            handle.write("No rows were rejected.\n")
            return Path(path)
        for source in sorted({item.source for item in load_result.rejections}):
            handle.write(f"{source}\n")
            handle.write("-" * len(source) + "\n")
            for rejection in sorted(
                    (item for item in load_result.rejections if item.source == source),
                    key=lambda item: (item.row_number, item.field)):
                handle.write("  " + rejection.describe() + "\n")
            handle.write("\n")
        handle.write("Reasons by category\n")
        handle.write("-------------------\n")
        for category, count in load_result.counts_by_category().items():
            handle.write(f"  {category:<22}{count}\n")
        handle.write(f"\n  {'rejected rows':<22}{load_result.rejected_rows}\n")
        handle.write(f"  {'accepted rows':<22}{load_result.accepted_rows}\n")
    return Path(path)
