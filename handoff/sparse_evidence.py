"""Fixed V2 station evidence: groups keyed by ticket, label and model set."""

from dataclasses import dataclass
from fractions import Fraction

from handoff.evidence import EvidenceSource
from storage import InvalidEvidence, InvalidInput, identifier


ScoreTally = tuple[Fraction, int]
ScoreColumn = tuple[ScoreTally, ...]


@dataclass(frozen=True)
class SparseContribution:
    ticket: str
    label: str
    count: int
    scores: dict[str, ScoreColumn]


@dataclass(frozen=True)
class SparseStationEvidence:
    package_id: str
    source: EvidenceSource
    contributions: tuple[SparseContribution, ...]


def _validate_column(column: object) -> tuple[ScoreColumn, int]:
    if not isinstance(column, (list, tuple)) or not column:
        raise InvalidEvidence('a score column must contain at least one score tally')
    seen = set()
    total = 0
    normalized = []
    for tally in column:
        if not isinstance(tally, (list, tuple)) or len(tally) != 2:
            raise InvalidEvidence('each score tally needs a score and a count')
        score, count = tally
        if not isinstance(score, Fraction):
            raise InvalidEvidence('a score tally needs an exact rational score')
        if type(count) is not int or count <= 0:
            raise InvalidEvidence('a score tally needs a positive integer count')
        if score in seen:
            raise InvalidEvidence('a score appears more than once in a column')
        seen.add(score)
        total += count
        normalized.append((score, count))
    return tuple(sorted(normalized)), total


def _normalize_contribution(contribution: SparseContribution) -> SparseContribution:
    if not isinstance(contribution, SparseContribution):
        raise InvalidEvidence('invalid sparse contribution')
    identifier(contribution.ticket, 'ticket number')
    if contribution.label not in ('positive', 'negative'):
        raise InvalidEvidence('invalid contribution label')
    if type(contribution.count) is not int or contribution.count <= 0:
        raise InvalidEvidence('a contribution count must be a positive integer')
    if not isinstance(contribution.scores, dict) or not contribution.scores:
        raise InvalidEvidence('each group needs at least one model column')
    columns: dict[str, ScoreColumn] = {}
    for model, column in contribution.scores.items():
        identifier(model, 'model name')
        normalized, total = _validate_column(column)
        if total != contribution.count:
            raise InvalidEvidence('each model column count must equal the group count')
        columns[model] = normalized
    return SparseContribution(contribution.ticket, contribution.label, contribution.count, columns)


def validate_sparse_evidence(evidence: SparseStationEvidence) -> SparseStationEvidence:
    if not isinstance(evidence, SparseStationEvidence) or not isinstance(evidence.source, EvidenceSource):
        raise InvalidEvidence('a sparse station package with a source is required')
    if not isinstance(evidence.contributions, tuple) or not evidence.contributions:
        raise InvalidEvidence('sparse station evidence is missing contributions')
    try:
        identifier(evidence.package_id, 'package id')
        identifier(evidence.source.origin, 'source origin')
        identifier(evidence.source.station, 'station')
        identifier(evidence.source.revision, 'source revision')
        groups = {}
        for contribution in evidence.contributions:
            normalized = _normalize_contribution(contribution)
            key = (normalized.ticket, normalized.label, tuple(sorted(normalized.scores)))
            if key in groups:
                raise InvalidEvidence('a ticket, label and model set combination appears more than once')
            groups[key] = normalized
    except InvalidInput as exc:
        raise InvalidEvidence(str(exc)) from exc
    ordered = tuple(sorted(
        groups.values(),
        key=lambda group: (group.ticket, group.label, tuple(sorted(group.scores))),
    ))
    return SparseStationEvidence(evidence.package_id, evidence.source, ordered)
