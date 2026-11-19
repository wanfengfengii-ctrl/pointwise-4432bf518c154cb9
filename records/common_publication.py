"""Atomic publication of common-support comparison reports."""

from dataclasses import dataclass
from fractions import Fraction
import json
import sqlite3

from analysis.common_jackknife import CommonDeletion, CommonDeletionResult
from records.common_provenance import initialize_common_provenance, save_common_sources
from records.common_receipts import initialize_common_receipts, save_common_receipt
from records.provenance import ReportSource
from records.receipts import ReportReceipt
from storage import MissingItem, PublicationFailed, require_sqlite_id, write_transaction


@dataclass(frozen=True)
class CommonReport:
    report_id: int
    models: tuple[str, ...]
    positive_count: int
    negative_count: int
    auc: tuple[Fraction, ...]
    deletions: tuple[CommonDeletion, ...]
    covariance: tuple[tuple[Fraction, ...], ...]


def initialize_common_records(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS common_reports (
            report_id INTEGER PRIMARY KEY,
            payload TEXT NOT NULL
        )
    ''')
    initialize_common_provenance(db)
    initialize_common_receipts(db)


def _encode_snapshot(models: tuple[str, ...], result: CommonDeletionResult) -> str:
    return json.dumps({
        'models': list(models),
        'positive_count': result.positive_count,
        'negative_count': result.negative_count,
        'auc': [str(value) for value in result.full_auc],
        'deletions': [[row.ticket, *[str(value) for value in row.auc]] for row in result.deletions],
        'covariance': [[str(value) for value in line] for line in result.covariance],
    }, ensure_ascii=False, separators=(',', ':'))


def publish_common_report(
    db: sqlite3.Connection,
    models: tuple[str, ...],
    result: CommonDeletionResult,
    sources: tuple[ReportSource, ...],
) -> tuple[CommonReport, ReportReceipt]:
    payload = _encode_snapshot(models, result)
    try:
        with write_transaction(db):
            cursor = db.execute('INSERT INTO common_reports(payload) VALUES (?)', (payload,))
            report_id = cursor.lastrowid
            save_common_sources(db, report_id, sources)
            receipt = save_common_receipt(db, report_id)
    except sqlite3.Error as exc:
        raise PublicationFailed('could not commit the common comparison report') from exc
    report = CommonReport(
        report_id, models, result.positive_count, result.negative_count,
        result.full_auc, result.deletions, result.covariance,
    )
    return report, receipt


def read_common_snapshot(db: sqlite3.Connection, report_id: int) -> CommonReport:
    require_sqlite_id(report_id, 'report id')
    row = db.execute('SELECT payload FROM common_reports WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise MissingItem(f'no such common report {report_id}')
    payload = json.loads(row[0])
    deletions = tuple(
        CommonDeletion(entry[0], tuple(Fraction(value) for value in entry[1:]))
        for entry in payload['deletions']
    )
    covariance = tuple(
        tuple(Fraction(value) for value in line) for line in payload['covariance']
    )
    return CommonReport(
        report_id,
        tuple(payload['models']),
        payload['positive_count'],
        payload['negative_count'],
        tuple(Fraction(value) for value in payload['auc']),
        deletions,
        covariance,
    )
