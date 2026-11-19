"""Sparse station snapshots: the last submitted value per model at a revision."""

from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from scoring.sparse import require_sparse_revision


@dataclass(frozen=True)
class SparseOccurrence:
    station: str
    occurrence: str
    ticket: str
    label: str
    scores: dict[str, Fraction]


@dataclass(frozen=True)
class SparseSnapshot:
    origin: str
    station: str
    revision: int
    occurrences: tuple[SparseOccurrence, ...]


def read_sparse_snapshot(db: sqlite3.Connection, station: str, revision: int) -> SparseSnapshot:
    require_sparse_revision(db, station, revision)
    origin = db.execute('SELECT origin FROM score_origin WHERE singleton = 1').fetchone()[0]
    identity_rows = db.execute(
        'SELECT occurrence, ticket, label FROM sparse_occurrence_registry WHERE station = ? ORDER BY occurrence',
        (station,),
    ).fetchall()
    occurrences: list[SparseOccurrence] = []
    for occurrence, ticket, label in identity_rows:
        rows = db.execute(
            '''
            SELECT model, score FROM sparse_score_versions
            WHERE station = ? AND occurrence = ? AND revision <= ?
            ORDER BY revision
            ''',
            (station, occurrence, revision),
        ).fetchall()
        latest: dict[str, Fraction] = {}
        for model, score in rows:
            latest[model] = Fraction(score)
        if latest:
            occurrences.append(SparseOccurrence(station, occurrence, ticket, label, latest))
    return SparseSnapshot(origin, station, revision, tuple(occurrences))
