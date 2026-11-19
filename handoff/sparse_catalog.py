"""Archive catalog for fixed V2 sparse station packages."""

from dataclasses import replace
import sqlite3

from handoff.sparse_evidence import SparseStationEvidence, validate_sparse_evidence
from handoff.sparse_package import decode_sparse_evidence, encode_sparse_evidence
from storage import InvalidEvidence, MissingItem, identifier, write_transaction

def initialize_sparse_handoff(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS sparse_station_packages (
            package_id TEXT PRIMARY KEY NOT NULL,
            origin TEXT NOT NULL,
            station TEXT NOT NULL,
            revision TEXT NOT NULL,
            payload TEXT NOT NULL,
            UNIQUE (origin, station, revision)
        )
    ''')


class SparseStationCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def save(self, evidence: SparseStationEvidence) -> SparseStationEvidence:
        evidence = validate_sparse_evidence(evidence)
        source = evidence.source
        try:
            with write_transaction(self.db):
                row = self.db.execute(
                    'SELECT payload FROM sparse_station_packages WHERE package_id = ?',
                    (evidence.package_id,),
                ).fetchone()
                if row is not None:
                    existing = decode_sparse_evidence(row[0])
                    if existing != evidence:
                        raise InvalidEvidence(
                            'the package id already refers to different sparse evidence')
                    return existing
                row = self.db.execute('''
                    SELECT payload FROM sparse_station_packages
                    WHERE origin = ? AND station = ? AND revision = ?
                ''', (source.origin, source.station, source.revision)).fetchone()
                if row is not None:
                    existing = decode_sparse_evidence(row[0])
                    if replace(evidence, package_id=existing.package_id) != existing:
                        raise InvalidEvidence('the source revision already has different sparse evidence')
                    return existing
                self.db.execute('''
                    INSERT INTO sparse_station_packages(package_id, origin, station, revision, payload)
                    VALUES (?, ?, ?, ?, ?)
                ''', (evidence.package_id, source.origin, source.station, source.revision,
                      encode_sparse_evidence(evidence)))
        except sqlite3.Error as exc:
            raise InvalidEvidence('the sparse station package could not be fixed in the archive') from exc
        return evidence

    def read(self, package_id: str) -> SparseStationEvidence:
        identifier(package_id, 'package id')
        row = self.db.execute(
            'SELECT payload FROM sparse_station_packages WHERE package_id = ?', (package_id,)
        ).fetchone()
        if row is None:
            raise MissingItem(f'no such sparse station package {package_id!r}')
        return decode_sparse_evidence(row[0])
