"""Provenance rows for common-support reports."""

import sqlite3

from records.provenance import ReportSource


def initialize_common_provenance(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS common_report_sources (
            report_id INTEGER NOT NULL REFERENCES common_reports(report_id),
            position INTEGER NOT NULL,
            package_id TEXT NOT NULL REFERENCES sparse_station_packages(package_id),
            station TEXT NOT NULL,
            origin TEXT NOT NULL,
            revision TEXT NOT NULL,
            PRIMARY KEY (report_id, position),
            UNIQUE (report_id, station)
        )
    ''')


def save_common_sources(db: sqlite3.Connection, report_id: int, sources: tuple[ReportSource, ...]) -> None:
    db.executemany('''
        INSERT INTO common_report_sources(report_id, position, package_id, station, origin, revision)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', ((report_id, index, source.package_id, source.station, source.origin, source.revision)
          for index, source in enumerate(sources)))


def read_common_sources(db: sqlite3.Connection, report_id: int) -> tuple[ReportSource, ...]:
    rows = db.execute('''
        SELECT package_id, station, origin, revision FROM common_report_sources
        WHERE report_id = ? ORDER BY position
    ''', (report_id,))
    return tuple(ReportSource(*row) for row in rows)
