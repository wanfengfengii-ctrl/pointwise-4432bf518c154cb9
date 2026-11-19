"""Partner-side acceptance and retrieval of sparse station packages."""

import sqlite3

from handoff.evidence import EvidenceSource
from handoff.sparse_catalog import SparseStationCatalog
from handoff.sparse_evidence import SparseStationEvidence
from handoff.sparse_package import decode_sparse_evidence
from storage import InvalidEvidence


def accept_sparse_station(
    db: sqlite3.Connection, payload: str, declared_source: EvidenceSource
) -> SparseStationEvidence:
    evidence = decode_sparse_evidence(payload)
    if not isinstance(declared_source, EvidenceSource) or evidence.source != declared_source:
        raise InvalidEvidence('the declared source does not match the sparse station package')
    return SparseStationCatalog(db).save(evidence)


def read_sparse_station(db: sqlite3.Connection, package_id: str) -> SparseStationEvidence:
    return SparseStationCatalog(db).read(package_id)
