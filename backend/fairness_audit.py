"""
Bias audit module.

This runs AFTER scoring, never before. It re-attaches demographic
metadata (inferred or self-reported) to the anonymized scores purely
to check for statistical skew -- the scoring engine itself never sees
this data, only the audit does.

The core method here is the "four-fifths rule" (also called the 80%
rule), the long-standing EEOC adverse-impact heuristic: if a group's
selection rate is less than 80% of the highest-scoring group's
selection rate, that's a flag for adverse impact and warrants human
review before the shortlist is finalized.

This is a teaching/demo implementation of a real compliance concept,
not a certified legal audit -- for a production system you'd want a
proper statistician and legal review on top of this.
"""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class GroupStats:
    group: str
    total: int = 0
    advanced: int = 0  # count of candidates above the shortlist threshold

    @property
    def selection_rate(self) -> float:
        return self.advanced / self.total if self.total else 0.0


@dataclass
class FairnessReport:
    threshold_score: int
    group_stats: dict[str, GroupStats] = field(default_factory=dict)
    flagged: bool = False
    flagged_groups: list[str] = field(default_factory=list)
    summary: str = ""


def run_fairness_audit(
    scores: dict[str, int],            # candidate_id -> score
    demographics: dict[str, str],      # candidate_id -> group label (e.g. "Group A")
    threshold_score: int = 70,
) -> FairnessReport:
    """
    Applies the four-fifths rule across whatever group labels are
    provided. Group labels are intentionally generic here (the demo
    uses self-reported categories from a sample dataset) -- in a real
    deployment this data must be collected and stored separately from
    the scoring pipeline, with its own consent and retention policy.
    """
    stats: dict[str, GroupStats] = defaultdict(lambda: GroupStats(group=""))

    for candidate_id, score in scores.items():
        group = demographics.get(candidate_id, "unknown")
        stats[group].group = group
        stats[group].total += 1
        if score >= threshold_score:
            stats[group].advanced += 1

    if not stats:
        return FairnessReport(threshold_score=threshold_score, summary="No data to audit.")

    best_rate = max(s.selection_rate for s in stats.values())
    flagged_groups = []

    if best_rate > 0:
        for group, s in stats.items():
            if s.total >= 5 and (s.selection_rate / best_rate) < 0.8:
                flagged_groups.append(group)

    flagged = len(flagged_groups) > 0
    if flagged:
        summary = (
            f"Adverse impact flagged for: {', '.join(flagged_groups)}. "
            f"These groups' selection rates fall below 80% of the "
            f"highest-performing group's rate at the {threshold_score} "
            f"score threshold. Recommend human review before finalizing "
            f"the shortlist."
        )
    else:
        summary = (
            f"No adverse impact detected at the {threshold_score} score "
            f"threshold (four-fifths rule). Continue to monitor across "
            f"larger candidate pools -- small samples can mask real skew."
        )

    return FairnessReport(
        threshold_score=threshold_score,
        group_stats=dict(stats),
        flagged=flagged,
        flagged_groups=flagged_groups,
        summary=summary,
    )
