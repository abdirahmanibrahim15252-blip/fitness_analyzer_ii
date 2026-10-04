"""The classification rules, built with inheritance and method overriding.

Every rule answers two questions: does this verdict fit the evidence, and
how do I explain it to a person? The analyzer asks the rules in priority
order and uses the first one that matches.
"""

from .analysis import describe_difference


class ClassificationRule:
    """Base class for one possible verdict."""

    label = "unclassified"

    def matches(self, facts):
        raise NotImplementedError("each rule must decide when it applies")

    def explain(self, facts):
        return f"The session met the conditions for {self.label}."

    def evaluate(self, facts):
        """The only method the analyzer calls. Subclasses never override it."""
        if self.matches(facts):
            return {"label": self.label, "explanation": self.explain(facts)}
        return None


class InsufficientDataRule(ClassificationRule):
    """Stops the program guessing when too little of the session survived."""

    label = "insufficient data"

    def __init__(self, minimum_usable=4, minimum_ratio=0.5):
        self.minimum_usable = minimum_usable
        self.minimum_ratio = minimum_ratio

    def matches(self, facts):
        return (facts["usable_windows"] < self.minimum_usable
                or facts["usable_ratio"] < self.minimum_ratio)

    def explain(self, facts):
        return (f"{facts['usable_windows']} of {facts['total_windows']} rows passed "
                f"validation. The program needs at least {self.minimum_usable} usable "
                f"windows and {self.minimum_ratio:.0%} of the rows before it trusts a "
                f"verdict, so it refuses to guess.")


class RecoveryRule(ClassificationRule):
    """Effort earlier in the session, and a clear cool down at the end."""

    label = "recovering"

    def matches(self, facts):
        return facts["recovery"]["detected"]

    def explain(self, facts):
        r = facts["recovery"]
        return (f"Heart rate peaked at {r['peak_heart_rate']:.0f} bpm, which is "
                f"{r['peak_elevation']:.0f} bpm above baseline, then fell to "
                f"{r['final_heart_rate']:.0f} bpm by the end. Only "
                f"{r['remaining_fraction']:.0%} of that rise is left, and movement "
                f"fell from {r['peak_activity']:.2f} to {r['final_activity']:.2f}. "
                f"The body was winding down after effort.")


class ThresholdRule(ClassificationRule):
    """Matches when average movement or heart rate elevation reaches a limit."""

    def __init__(self, activity_threshold, elevation_threshold):
        self.activity_threshold = activity_threshold
        self.elevation_threshold = elevation_threshold

    def matches(self, facts):
        return (facts["average_activity"] >= self.activity_threshold
                or facts["heart_rate_elevation"] >= self.elevation_threshold)

    def explain(self, facts):
        reasons = []
        if facts["average_activity"] >= self.activity_threshold:
            reasons.append(f"average activity {facts['average_activity']:.2f} reached "
                           f"the limit of {self.activity_threshold:.2f}")
        if facts["heart_rate_elevation"] >= self.elevation_threshold:
            reasons.append("heart rate averaged "
                           f"{describe_difference(facts['heart_rate_elevation'], ' bpm')}, "
                           f"past the limit of {self.elevation_threshold:.0f} bpm")
        return f"Classified as {self.label} because " + " and ".join(reasons) + "."


class HighActivityRule(ThresholdRule):
    label = "high activity"

    def __init__(self, activity_threshold=0.67, elevation_threshold=45.0):
        super().__init__(activity_threshold, elevation_threshold)


class ModerateActivityRule(ThresholdRule):
    label = "moderate activity"

    def __init__(self, activity_threshold=0.30, elevation_threshold=15.0):
        super().__init__(activity_threshold, elevation_threshold)


class RestingRule(ClassificationRule):
    """The fallback: trustworthy data that never reached the moderate limits."""

    label = "resting"

    def matches(self, facts):
        return True

    def explain(self, facts):
        return (f"Average activity stayed at {facts['average_activity']:.2f} and heart "
                f"rate was {describe_difference(facts['heart_rate_elevation'], ' bpm')}. "
                f"Neither reached the moderate activity limits, so the body was at rest.")
