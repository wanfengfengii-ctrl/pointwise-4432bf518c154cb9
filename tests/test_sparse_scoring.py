from fractions import Fraction

from handoff.sparse_evidence import SparseStationEvidence
from handoff.sparse_package import decode_sparse_evidence, encode_sparse_evidence
from review import (BoardTicket, admit_board, encode_sparse_evidence as review_encode,
                    freeze_sparse_station, record_sparse_scores)
from scoring.sparse_snapshots import read_sparse_snapshot
from storage import Conflict, InvalidInput, MissingItem
from tests.support import ReviewTest, scenario


class SparseScoringTests(ReviewTest):
    def _admit(self, ticket='P', station='East'):
        return admit_board(self.source, BoardTicket(ticket, f'film-{ticket}'), station)

    def test_named_sparse_scores_are_append_only_per_model(self):
        self._admit()
        first = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1',
                                     {'A': 0, 'B': 1})
        second = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's2',
                                      {'C': 2})
        third = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's3',
                                     {'B': 3})
        self.assertLess(first, second)
        self.assertLess(second, third)
        self.assertEqual(
            read_sparse_snapshot(self.source, 'East', first).occurrences[0].scores,
            {'A': Fraction(0), 'B': Fraction(1)},
        )
        self.assertEqual(
            read_sparse_snapshot(self.source, 'East', second).occurrences[0].scores,
            {'A': Fraction(0), 'B': Fraction(1), 'C': Fraction(2)},
        )
        self.assertEqual(
            read_sparse_snapshot(self.source, 'East', third).occurrences[0].scores,
            {'A': Fraction(0), 'B': Fraction(3), 'C': Fraction(2)},
        )
        scenario('c1.sparse_supplement', {'submissions': ['s1', 's2', 's3']},
                 [['A=0,B=1'], ['A=0,B=1,C=2'], ['A=0,B=3,C=2']],
                 [[f'{model}={value}' for model, value in
                   read_sparse_snapshot(self.source, 'East', revision).occurrences[0].scores.items()]
                  for revision in (first, second, third)],
                 True, third > second > first,
                 ['scoring/sparse.py', 'scoring/sparse_snapshots.py'],
                 'Each submission only changes the models it carries; the freeze boundary takes the last visible value.')

    def test_equivalent_replay_returns_original_revision(self):
        self._admit()
        revision = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1',
                                        {'A': 0, 'B': '2/2'})
        replay = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1',
                                      {'B': Fraction(1), 'A': Fraction(0)})
        self.assertEqual(replay, revision)
        scenario('c2.sparse_replay', {'submission_id': 's1'}, revision, replay, True, replay == revision,
                 ['scoring/sparse.py'],
                 'Mapping order and rational spelling do not matter; the equivalent replay keeps the first revision.')

    def test_reused_submission_id_with_different_params_is_conflict(self):
        self._admit()
        record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1', {'A': 0, 'B': 1})
        record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's3', {'B': 3})
        with self.assertRaises(Conflict):
            record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's3',
                                 {'A': 0, 'B': 3})
        with self.assertRaises(Conflict):
            record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'negative', 's9', {'A': 1})
        with self.assertRaises(Conflict):
            record_sparse_scores(self.source, 'East', 'P', 'other-occ', 'positive', 's1', {'A': 9})

    def test_first_submission_fixes_ticket_and_label(self):
        self._admit('P')
        self._admit('Q')
        record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1', {'A': 0})
        with self.assertRaises(Conflict):
            record_sparse_scores(self.source, 'East', 'Q', 'occ-1', 'positive', 's2', {'A': 1})
        with self.assertRaises(Conflict):
            record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'negative', 's2', {'A': 1})

    def test_invalid_sparse_input_and_missing_admission(self):
        self._admit()
        for scores in ({}, {'A': True}, {'A': 1.5}, {'A': '1/0'}, {'': 1}):
            with self.subTest(scores=scores), self.assertRaises(InvalidInput):
                record_sparse_scores(self.source, 'East', 'P', 'occ-bad', 'positive', 'sb', scores)
        with self.assertRaises(InvalidInput):
            record_sparse_scores(self.source, 'East', 'P', 'occ-bad', 'unknown', 'sb', {'A': 1})
        with self.assertRaises(MissingItem):
            record_sparse_scores(self.source, 'East', 'Z', 'occ-z', 'positive', 'sz', {'A': 1})

    def test_zero_is_a_valid_score(self):
        self._admit()
        revision = record_sparse_scores(self.source, 'East', 'P', 'occ-z', 'negative', 'sz',
                                        {'A': 0, 'B': Fraction(0)})
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        group = next(group for group in package.contributions
                     if group.ticket == 'P' and group.label == 'negative')
        self.assertEqual(group.count, 1)
        self.assertEqual(set(group.scores), {'A', 'B'})
        self.assertTrue(all(column == ((Fraction(0), 1),) for column in group.scores.values()))

    def test_freeze_groups_by_ticket_label_and_model_set(self):
        self._admit('P')
        self._admit('Q')
        record_sparse_scores(self.source, 'East', 'P', 'p+', 'positive', 's1', {'A': 2, 'B': 2})
        record_sparse_scores(self.source, 'East', 'P', 'p-only', 'positive', 's2', {'C': 5})
        revision = record_sparse_scores(self.source, 'East', 'Q', 'q-', 'negative', 's3',
                                        {'A': 1, 'B': 1, 'C': 1})
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        self.assertIsInstance(package, SparseStationEvidence)
        keys = {(group.ticket, group.label, tuple(sorted(group.scores))) for group in package.contributions}
        self.assertEqual(keys, {
            ('P', 'positive', ('A', 'B')),
            ('P', 'positive', ('C',)),
            ('Q', 'negative', ('A', 'B', 'C')),
        })
        self.assertEqual(package.source.revision, str(revision))
        self.assertEqual(freeze_sparse_station(self.source, self.archive, 'East', revision), package)
        roundtrip = decode_sparse_evidence(encode_sparse_evidence(package))
        self.assertEqual(roundtrip, package)
        self.assertEqual(review_encode(package), encode_sparse_evidence(package))
        scenario('c3.sparse_freeze_groups', {'revision': revision}, sorted(map(str, keys)),
                 sorted(str(key) for key in keys), True, roundtrip == package,
                 ['scoring/sparse_snapshots.py', 'handoff/sparse_freeze.py', 'handoff/sparse_package.py'],
                 'The fixed package keeps separate groups per ticket, label and complete model set.')

    def test_unknown_sparse_revision_or_station_is_missing(self):
        self._admit()
        revision = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1', {'A': 1})
        with self.assertRaises(MissingItem):
            freeze_sparse_station(self.source, self.archive, 'East', revision + 10)
        with self.assertRaises(MissingItem):
            freeze_sparse_station(self.source, self.archive, 'West', revision)
        self.assertEqual(self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 0)

    def test_sparse_and_v1_coexist_in_one_source(self):
        from review import ModelPair, record_pair

        self._admit()
        sparse_revision = record_sparse_scores(self.source, 'East', 'P', 'sparse-occ',
                                               'positive', 's1', {'A': 1})
        pair_revision = record_pair(self.source, 'East', 'P', 'pair-occ', 'positive',
                                    ModelPair('A', 'B'), {'A': 1, 'B': 2})
        sparse_package = freeze_sparse_station(self.source, self.archive, 'East', sparse_revision)
        from review import freeze_station
        v1_package = freeze_station(self.source, self.archive, 'East', pair_revision.revision)
        self.assertNotEqual(sparse_package.package_id, v1_package.package_id)
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 1)
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM station_packages').fetchone()[0], 1)
        # reopening the source keeps both ledgers
        self.reopen_source()
        self.assertEqual(read_sparse_snapshot(self.source, 'East', sparse_revision).origin, 'test-center')

    def test_sparse_freeze_after_source_closes_is_not_needed_but_archive_keeps_package(self):
        self._admit()
        revision = record_sparse_scores(self.source, 'East', 'P', 'occ-1', 'positive', 's1', {'A': 1})
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        self.source.close()
        self.reopen_archive()
        from review import read_sparse_station
        self.assertEqual(read_sparse_station(self.archive, package.package_id), package)

    def test_v1_and_sparse_revisions_share_one_sequence_and_cannot_cross_freeze(self):
        from review import ModelPair, freeze_station, record_pair

        self._admit()
        v1_first = record_pair(self.source, 'East', 'P', 'pair-1', 'positive',
                                ModelPair('A', 'B'), {'A': 1, 'B': 2})
        sparse_revision = record_sparse_scores(self.source, 'East', 'P', 'sparse-1',
                                               'positive', 's1', {'A': 1})
        v1_second = record_pair(self.source, 'East', 'P', 'pair-2', 'negative',
                                ModelPair('A', 'B'), {'A': 1, 'B': 2})
        self.assertEqual(
            [v1_first.revision, sparse_revision, v1_second.revision], [1, 2, 3])
        with self.assertRaises(MissingItem):
            freeze_sparse_station(self.source, self.archive, 'East', v1_first.revision)
        with self.assertRaises(MissingItem):
            freeze_sparse_station(self.source, self.archive, 'East', v1_second.revision)
        with self.assertRaises(MissingItem):
            freeze_station(self.source, self.archive, 'East', sparse_revision)
        self.assertTrue(freeze_station(self.source, self.archive, 'East', v1_second.revision).package_id)
        self.assertTrue(
            freeze_sparse_station(self.source, self.archive, 'East', sparse_revision).package_id)
