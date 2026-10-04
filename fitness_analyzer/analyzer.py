"""Turning a Session into a structured result."""

from .analysis import compare_with_baseline, detect_recovery, summarise
from .models import MEASURED_FIELDS
from .rules import (ClassificationRule, HighActivityRule, InsufficientDataRule,
                    ModerateActivityRule, RecoveryRule, RestingRule)
from .validation import session_year


class SessionAnalyzer:
    """Composes an ordered list of rules and applies them to a session."""

    def __init__(self, rules):
        rules = list(rules)
        if not rules or not all(isinstance(rule, ClassificationRule) for rule in rules):
            raise ValueError("SessionAnalyzer needs at least one ClassificationRule")
        self._rules = rules

    @classmethod
    def with_default_rules(cls):
        """The order matters: data quality first, then the trend, then intensity."""
        return cls([
            InsufficientDataRule(),
            RecoveryRule(),
            HighActivityRule(),
            ModerateActivityRule(),
            RestingRule(),
        ])

    @property
    def rule_labels(self):
        return [rule.label for rule in self._rules]

    def analyze(self, session):
        """Return the structured result for one session."""
        participant = session.participant
        usable = len(session)
        total = session.total_rows
        ratio = usable / total if total else 0.0

        summaries = {field: summarise(session.values(field))
                     for field in MEASURED_FIELDS}
        comparison = {
            field: compare_with_baseline(summaries[field]["average"], baseline)
            for field, baseline in participant.baselines().items()
        }
        recovery = detect_recovery(session.values("heart_rate"),
                                   session.values("activity_level"),
                                   participant.baseline_heart_rate)
        facts = {
            "total_windows": total,
            "usable_windows": usable,
            "usable_ratio": ratio,
            "heart_rate_elevation": comparison["heart_rate"]["difference"],
            "average_activity": summaries["activity_level"]["average"],
            "recovery": recovery,
        }
        verdict = self._classify(facts)

        return {
            "session_id": session.session_id,
            "session_year": session_year(session.session_id),
            "sources": list(session.sources),
            "participant_id": participant.participant_id,
            "participant_name": participant.name,
            "classification": verdict["label"],
            "explanation": verdict["explanation"],
            "windows": {
                "total": total,
                "usable": usable,
                "rejected": session.rejected_rows,
                "usable_percent": round(ratio * 100, 1),
            },
            "summaries": summaries,
            "comparison": comparison,
            "recovery": recovery,
        }

    def _classify(self, facts):
        for rule in self._rules:
            verdict = rule.evaluate(facts)
            if verdict is not None:
                return verdict
        return {"label": "insufficient data",
                "explanation": "No rule matched the evidence."}
