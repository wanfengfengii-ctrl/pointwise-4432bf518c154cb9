"""Version 2 sparse evidence exchange codec."""

import json

from boards.labels import parse_label
from handoff.evidence import EvidenceSource
from handoff.package import _array, _object, _unique_fields
from handoff.sparse_evidence import (
    ScoreColumn,
    SparseContribution,
    SparseStationEvidence,
    validate_sparse_evidence,
)
from scoring.pairs import parse_score
from storage import InvalidEvidence, InvalidInput


SPARSE_PACKAGE_VERSION = 2


def encode_sparse_evidence(evidence: SparseStationEvidence) -> str:
    evidence = validate_sparse_evidence(evidence)
    payload = {
        'version': SPARSE_PACKAGE_VERSION,
        'package_id': evidence.package_id,
        'source': {
            'origin': evidence.source.origin,
            'station': evidence.source.station,
            'revision': evidence.source.revision,
        },
        'contributions': [
            {
                'ticket': contribution.ticket,
                'label': contribution.label,
                'count': contribution.count,
                'scores': {
                    model: [[str(score), count] for score, count in column]
                    for model, column in sorted(contribution.scores.items())
                },
            }
            for contribution in evidence.contributions
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _positive_int(value: object, description: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidEvidence(f'{description} must be a positive integer')
    return value


def _decode_column(value: object, count: int) -> ScoreColumn:
    tallies = []
    total = 0
    seen = set()
    for entry in _array(value, 'score column'):
        raw_score, multiplicity = _array(entry, 'score tally', 2)
        if not isinstance(raw_score, str):
            raise InvalidEvidence('package scores must be rational strings')
        score = parse_score(raw_score)
        multiplicity = _positive_int(multiplicity, 'a score multiplicity')
        if score in seen:
            raise InvalidEvidence('a score appears more than once in a column')
        seen.add(score)
        total += multiplicity
        tallies.append((score, multiplicity))
    if not tallies or total != count:
        raise InvalidEvidence('the column multiplicities must match the group count')
    return tuple(sorted(tallies))


def _decode_contribution(value: object) -> SparseContribution:
    group = _object(value, {'ticket', 'label', 'count', 'scores'}, 'sparse contribution')
    count = _positive_int(group['count'], 'the group count')
    raw_scores = group['scores']
    if not isinstance(raw_scores, dict) or not raw_scores:
        raise InvalidEvidence('each group needs a nonempty scores object')
    try:
        label = parse_label(group['label']).value
        scores = {model: _decode_column(column, count) for model, column in raw_scores.items()}
    except InvalidInput as exc:
        raise InvalidEvidence(str(exc)) from exc
    return SparseContribution(group['ticket'], label, count, scores)


def decode_sparse_evidence(payload: object) -> SparseStationEvidence:
    if not isinstance(payload, str):
        raise InvalidEvidence('a sparse station package must be JSON text')
    try:
        data = json.loads(payload, object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError) as exc:
        raise InvalidEvidence('invalid sparse station package JSON') from exc
    data = _object(data, {'version', 'package_id', 'source', 'contributions'}, 'sparse station package')
    if type(data['version']) is not int or data['version'] != SPARSE_PACKAGE_VERSION:
        raise InvalidEvidence('unsupported sparse station package version')
    source = _object(data['source'], {'origin', 'station', 'revision'}, 'package source')
    contributions = tuple(
        _decode_contribution(group) for group in _array(data['contributions'], 'contributions')
    )
    if not contributions:
        raise InvalidEvidence('a sparse station package needs at least one contribution')
    return validate_sparse_evidence(
        SparseStationEvidence(data['package_id'], EvidenceSource(**source), contributions)
    )
