"""Standalone calculations. Each function takes plain numbers and returns plain data."""

from statistics import mean


def summarise(values):
    """Count, average, minimum and maximum of a list of numbers."""
    if not values:
        return {"count": 0, "average": None, "minimum": None, "maximum": None}
    return {
        "count": len(values),
        "average": round(mean(values), 2),
        "minimum": min(values),
        "maximum": max(values),
    }


def compare_with_baseline(average, baseline):
    """Compare a session average with a personal reference value."""
    if average is None:
        return {"baseline": baseline, "average": None,
                "difference": None, "percent_change": None}
    difference = average - baseline
    percent = difference / baseline * 100 if baseline else None
    return {
        "baseline": baseline,
        "average": average,
        "difference": round(difference, 2),
        "percent_change": None if percent is None else round(percent, 1),
    }


def detect_recovery(heart_rates, activity_levels, baseline_heart_rate,
                    minimum_windows=4, minimum_peak_elevation=25.0,
                    maximum_remaining_fraction=0.40,
                    maximum_activity_fraction=0.50):
    """Decide whether the session ends in a cool down.

    Assignment I compared the first third of a session with the last third.
    That works for a session which starts hard, but it misreads a session
    that opens with a warm up, because the quiet opening pulls the early
    average down and hides the fall at the end.

    This version measures the fall from the session's own peak instead:
    there must have been real effort, the peak must happen before the final
    phase, and by the end both heart rate and movement must have dropped
    close to the participant's normal level.
    """
    if len(heart_rates) != len(activity_levels):
        raise ValueError("heart_rates and activity_levels must have the same length")
    result = {
        "detected": False, "peak_heart_rate": None, "peak_elevation": None,
        "final_heart_rate": None, "remaining_elevation": None,
        "remaining_fraction": None, "peak_activity": None,
        "final_activity": None, "activity_fraction": None,
    }
    if len(heart_rates) < minimum_windows:
        return result

    phase = max(1, len(heart_rates) // 3)
    peak_index = heart_rates.index(max(heart_rates))
    peak_heart_rate = heart_rates[peak_index]
    peak_elevation = peak_heart_rate - baseline_heart_rate
    final_heart_rate = mean(heart_rates[-phase:])
    remaining_elevation = final_heart_rate - baseline_heart_rate
    peak_activity = max(activity_levels)
    final_activity = mean(activity_levels[-phase:])

    remaining_fraction = (remaining_elevation / peak_elevation
                          if peak_elevation > 0 else None)
    activity_fraction = (final_activity / peak_activity
                         if peak_activity > 0 else 0.0)

    result.update({
        "peak_heart_rate": peak_heart_rate,
        "peak_elevation": round(peak_elevation, 1),
        "final_heart_rate": round(final_heart_rate, 1),
        "remaining_elevation": round(remaining_elevation, 1),
        "remaining_fraction": (None if remaining_fraction is None
                               else round(remaining_fraction, 2)),
        "peak_activity": round(peak_activity, 2),
        "final_activity": round(final_activity, 2),
        "activity_fraction": round(activity_fraction, 2),
    })
    result["detected"] = (
        peak_elevation >= minimum_peak_elevation
        and peak_index < len(heart_rates) - phase
        and remaining_fraction is not None
        and remaining_fraction <= maximum_remaining_fraction
        and activity_fraction <= maximum_activity_fraction
    )
    return result


def describe_difference(difference, unit="", digits=1):
    """Turn a signed difference into words, such as '28.4 bpm above baseline'."""
    if difference is None:
        return "not available"
    size = abs(difference)
    if round(size, digits) == 0:
        return "level with baseline"
    direction = "above" if difference > 0 else "below"
    return f"{size:.{digits}f}{unit} {direction} baseline"
