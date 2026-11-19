"""Named, sparse score intake for the V2 common-support workflow.

A submission carries scores for any nonempty subset of named models.  The first
submission seen for a station occurrence fixes its central ticket and label;
later submissions may add models or correct already submitted models, but only
for the same occurrence identity.
"""

from collections.abc import Mapping
from fractions import Fraction
import sqlite3

from boards.labels import Label, parse_label
from boards.stations import require_admission
from scoring.pairs import parse_score
from storage import Conflict, InvalidInput, MissingItem, identifier, require_sqlite_id, write_transaction


def initialize_sparse(db: sqlite3.Connection) -> None:
    # score_revision_sequence is created by initialize_scoring, which always runs first.
    db.execute('''
        CREATE TABLE IF NOT EXISTS sparse_occurrence_registry (
            station TEXT NOT NULL,
            occurrence TEXT NOT NULL,
            ticket TEXT NOT NULL,
            label TEXT NOT NULL CHECK (label IN ('positive', 'negative')),
            PRIMARY KEY (station, occurrence),
            FOREIGN KEY (ticket, station) REFERENCES station_admissions(ticket, station)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS sparse_submissions (
            revision INTEGER PRIMARY KEY
                REFERENCES score_revision_sequence(revision),
            station TEXT NOT NULL,
            submission_id TEXT NOT NULL,
            occurrence TEXT NOT NULL,
            UNIQUE (station, submission_id),
            FOREIGN KEY (station, occurrence) REFERENCES sparse_occurrence_registry(station, occurrence)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS sparse_score_versions (
            revision INTEGER NOT NULL,
            station TEXT NOT NULL,
            occurrence TEXT NOT NULL,
            model TEXT NOT NULL,
            score TEXT NOT NULL,
            PRIMARY KEY (revision, station, occurrence, model),
            FOREIGN KEY (station, occurrence) REFERENCES sparse_occurrence_registry(station, occurrence)
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS sparse_versions_by_station
        ON sparse_score_versions(station, revision)
    ''')


def _normalize_sparse_input(
    station: str, ticket: str, occurrence: str, label: object, submission_id: str,
    scores: object,
) -> tuple[str, str, str, Label, str, dict[str, Fraction]]:
    identifier(station, 'station')
    identifier(ticket, 'ticket number')
    identifier(occurrence, 'occurrence number')
    identifier(submission_id, 'submission id')
    parsed_label = parse_label(label)
    if not isinstance(scores, Mapping) or not scores:
        raise InvalidInput('scores must be a nonempty mapping of model names to scores')
    normalized: dict[str, Fraction] = {}
    for model, value in scores.items():
        identifier(model, 'model name')
        normalized[model] = parse_score(value)
    return station, ticket, occurrence, parsed_label, submission_id, normalized


def record_sparse_scores(
    db: sqlite3.Connection,
    station: str,
    ticket: str,
    occurrence: str,
    label: object,
    submission_id: str,
    scores: Mapping[str, object],
) -> int:
    station, ticket, occurrence, parsed_label, submission_id, normalized = _normalize_sparse_input(
        station, ticket, occurrence, label, submission_id, scores
    )
    with write_transaction(db):
        require_admission(db, station, ticket)
        replay = db.execute(
            'SELECT revision, occurrence FROM sparse_submissions WHERE station = ? AND submission_id = ?',
            (station, submission_id),
        ).fetchone()
        if replay is not None:
            revision, existing_occurrence = replay
            if existing_occurrence != occurrence:
                raise Conflict('the submission id was already used for a different occurrence')
            registered = db.execute(
                'SELECT ticket, label FROM sparse_occurrence_registry WHERE station = ? AND occurrence = ?',
                (station, occurrence),
            ).fetchone()
            if registered is not None and registered != (ticket, parsed_label.value):
                raise Conflict('the submission changes the fixed ticket or label')
            existing = {
                model: Fraction(score)
                for model, score in db.execute(
                    'SELECT model, score FROM sparse_score_versions WHERE station = ? AND revision = ?',
                    (station, revision),
                )
            }
            if existing != normalized:
                raise Conflict('the submission id was already used with different scores')
            return revision

        registered = db.execute(
            'SELECT ticket, label FROM sparse_occurrence_registry WHERE station = ? AND occurrence = ?',
            (station, occurrence),
        ).fetchone()
        if registered is None:
            db.execute(
                'INSERT INTO sparse_occurrence_registry(station, occurrence, ticket, label) VALUES (?, ?, ?, ?)',
                (station, occurrence, ticket, parsed_label.value),
            )
        elif registered != (ticket, parsed_label.value):
            raise Conflict('the ticket and label of an occurrence are fixed by its first submission')

        cursor = db.execute('INSERT INTO score_revision_sequence DEFAULT VALUES')
        revision = cursor.lastrowid
        db.execute(
            'INSERT INTO sparse_submissions(revision, station, submission_id, occurrence) VALUES (?, ?, ?, ?)',
            (revision, station, submission_id, occurrence),
        )
        db.executemany(
            'INSERT INTO sparse_score_versions(revision, station, occurrence, model, score) VALUES (?, ?, ?, ?, ?)',
            ((revision, station, occurrence, model, str(score)) for model, score in normalized.items()),
        )
    return revision


def require_sparse_revision(db: sqlite3.Connection, station: str, revision: int) -> None:
    identifier(station, 'station')
    require_sqlite_id(revision, 'score revision')
    row = db.execute(
        'SELECT 1 FROM sparse_submissions WHERE station = ? AND revision = ?',
        (station, revision),
    ).fetchone()
    if row is None:
        raise MissingItem(f'no sparse score revision {revision} for station {station!r}')
