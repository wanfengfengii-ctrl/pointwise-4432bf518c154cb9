"""Freeze a sparse source revision into an immutable V2 station package."""

from collections import Counter
from hashlib import sha256
import json
import sqlite3

from handoff.evidence import EvidenceSource
from handoff.sparse_evidence import ScoreColumn, SparseContribution, SparseStationEvidence
from handoff.sparse_catalog import SparseStationCatalog
from scoring.sparse_snapshots import read_sparse_snapshot


def sparse_package_id(source: EvidenceSource) -> str:
    identity = json.dumps([source.origin, source.station, source.revision], separators=(',', ':'))
    return 'sparse-' + sha256(identity.encode('utf-8')).hexdigest()


def _build_contributions(snapshot) -> tuple[SparseContribution, ...]:
    groups: dict[tuple[str, str, tuple[str, ...]], dict[str, Counter]] = {}
    for occurrence in snapshot.occurrences:
        models = tuple(sorted(occurrence.scores))
        key = occurrence.ticket, occurrence.label, models
        columns = groups.setdefault(key, {model: Counter() for model in models})
        for model in models:
            columns[model][occurrence.scores[model]] += 1
    contributions = []
    for (ticket, label, models), columns in sorted(groups.items()):
        count = sum(columns[models[0]].values())
        scores: dict[str, ScoreColumn] = {
            model: tuple(sorted(columns[model].items())) for model in models
        }
        contributions.append(SparseContribution(ticket, label, count, scores))
    return tuple(contributions)


def freeze_sparse_station(
    source_db: sqlite3.Connection, archive_db: sqlite3.Connection, station: str, revision: int
) -> SparseStationEvidence:
    snapshot = read_sparse_snapshot(source_db, station, revision)
    source = EvidenceSource(snapshot.origin, snapshot.station, str(snapshot.revision))
    evidence = SparseStationEvidence(sparse_package_id(source), source, _build_contributions(snapshot))
    return SparseStationCatalog(archive_db).save(evidence)
