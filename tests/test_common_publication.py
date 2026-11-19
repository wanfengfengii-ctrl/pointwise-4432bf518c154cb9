import json
import sqlite3

from review import (BoardTicket, admit_board, freeze_sparse_station, issue_common_comparison,
                    open_source, read_common_report, record_sparse_scores)
from storage import MissingItem, PublicationFailed
from tests.support import ReviewTest, scenario


def reject_common_commit(db):
    db.execute('CREATE TABLE allowed_common_links (report_id INTEGER PRIMARY KEY)')
    db.execute('''
        CREATE TABLE pending_common_links (
            report_id INTEGER REFERENCES allowed_common_links(report_id)
            DEFERRABLE INITIALLY DEFERRED
        )
    ''')
    db.execute('''
        CREATE TRIGGER check_common_commit AFTER INSERT ON common_report_receipts
        BEGIN
            INSERT INTO pending_common_links(report_id) VALUES (NEW.report_id);
        END
    ''')


class CommonPublicationTests(ReviewTest):
    def _seed(self, station='East'):
        for ticket in ('P', 'Q'):
            admit_board(self.source, BoardTicket(ticket, f'film-{ticket}'), station)
        rows = [
            ('P', 'p+', 'positive', {'A': 2, 'B': 0}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 2}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
        ]
        revision = None
        for index, (ticket, occurrence, label, scores) in enumerate(rows):
            revision = record_sparse_scores(
                self.source, station, ticket, occurrence, label, f's{index}', scores)
        return freeze_sparse_station(self.source, self.archive, station, revision)

    def _common_counts(self):
        tables = ('common_reports', 'common_report_sources', 'common_report_receipts')
        return tuple(self.archive.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                     for table in tables)

    def test_failed_commit_has_no_partial_result_and_retries(self):
        package = self._seed()
        reject_common_commit(self.archive)
        with self.assertRaises(PublicationFailed) as caught:
            issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        self.assertIsInstance(caught.exception.__cause__, sqlite3.IntegrityError)
        self.assertFalse(self.archive.in_transaction)
        self.assertEqual(self._common_counts(), (0, 0, 0))
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM pending_common_links').fetchone()[0], 0)

        self.archive.close()
        repair = sqlite3.connect(self.archive_path)
        repair.execute('DROP TRIGGER check_common_commit')
        repair.execute('DROP TABLE pending_common_links')
        repair.execute('DROP TABLE allowed_common_links')
        repair.commit()
        repair.close()
        self.archive = self._track(self._open_archive())

        delivery = issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        self.assertEqual(self._common_counts(), (1, 1, 1))
        self.assertEqual(read_common_report(self.archive, delivery.report.report_id), delivery)
        scenario('c8.common_retry', {'constraint': 'deferred foreign key on common receipt'},
                 'PUBLICATION_FAILED->OK', caught.exception.code + '->OK', (1, 1, 1),
                 self._common_counts(),
                 ['records/common_publication.py', 'records/common_receipts.py'],
                 'The rejected commit leaves nothing; the same request retries successfully after reopen.')

    def _open_archive(self):
        from review import open_archive
        return open_archive(self.archive_path)

    def test_old_report_survives_correction_and_reopen(self):
        package = self._seed()
        first = issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        first_id = first.report.report_id
        first_json = read_common_report(self.archive, first_id, as_json=True)

        corrected_revision = record_sparse_scores(
            self.source, 'East', 'P', 'p+', 'positive', 'correct-p', {'A': 2, 'B': 2})
        self.source.close()
        self.reopen_archive()
        revised_package = freeze_sparse_station(
            open_source(self.source_path, origin='test-center'), self.archive, 'East',
            corrected_revision)
        self.assertNotEqual(revised_package.package_id, package.package_id)
        second = issue_common_comparison(
            self.archive, [revised_package.package_id], ['A', 'B'])
        self.assertNotEqual(second.report.report_id, first_id)

        self.reopen_archive()
        restored = read_common_report(self.archive, first_id)
        self.assertEqual(restored, first)
        self.assertEqual(read_common_report(self.archive, first_id, as_json=True), first_json)
        exported = json.loads(first_json)
        self.assertEqual(exported['sources'][0]['package_id'], package.package_id)
        self.assertEqual(exported['receipt']['receipt_id'], f'common-receipt-{first_id}')
        scenario('c9.common_reopen', {'old_report': first_id, 'new_report': second.report.report_id},
                 package.package_id, exported['sources'][0]['package_id'],
                 True, restored == first,
                 ['records/common_publication.py', 'records/common_retrieval.py'],
                 'Corrections and reopened archives keep the original report id, selection and receipt.')

    def test_unknown_common_report_is_missing(self):
        for as_json in (False, True):
            with self.assertRaises(MissingItem):
                read_common_report(self.archive, 771, as_json=as_json)
