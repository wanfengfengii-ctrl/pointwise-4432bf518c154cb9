"""Receipts for common-support reports."""

import sqlite3

from records.receipts import ReportReceipt
from storage import MissingItem


def initialize_common_receipts(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS common_report_receipts (
            report_id INTEGER PRIMARY KEY REFERENCES common_reports(report_id),
            receipt_id TEXT NOT NULL UNIQUE
        )
    ''')


def save_common_receipt(db: sqlite3.Connection, report_id: int) -> ReportReceipt:
    receipt = ReportReceipt(report_id, f'common-receipt-{report_id}')
    db.execute(
        'INSERT INTO common_report_receipts(report_id, receipt_id) VALUES (?, ?)',
        (receipt.report_id, receipt.receipt_id),
    )
    return receipt


def read_common_receipt(db: sqlite3.Connection, report_id: int) -> ReportReceipt:
    row = db.execute(
        'SELECT receipt_id FROM common_report_receipts WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise MissingItem(f'no receipt for common report {report_id}')
    return ReportReceipt(report_id, row[0])
