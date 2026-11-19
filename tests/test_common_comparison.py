import json
from fractions import Fraction

from common_support_examples import MODELS, partner_cases
from review import (BoardTicket, EvidenceSource, accept_sparse_station, admit_board,
                    freeze_sparse_station, issue_common_comparison, issue_comparison,
                    read_common_report, record_sparse_scores)
from storage import InsufficientEvidence, InvalidInput, InvalidSelection
from tests.support import ReviewTest, scenario


class CommonComparisonTests(ReviewTest):
    def _seed_sparse(self, station, rows):
        revisions = []
        for ticket, occurrence, label, scores in rows:
            admit_board(self.source, BoardTicket(ticket, f'film-{ticket}'), station)
        for index, (ticket, occurrence, label, scores) in enumerate(rows):
            revisions.append(record_sparse_scores(
                self.source, station, ticket, occurrence, label, f'{station}-s{index}', scores))
        return revisions[-1]

    def test_partner_cases_match_hand_calculated_auc(self):
        for name in ('high', 'low'):
            with self.subTest(name=name):
                case = partner_cases()[name]
                package = case['package']
                accepted = accept_sparse_station(
                    self.archive, json.dumps(package), EvidenceSource(**package['source']))
                delivery = issue_common_comparison(self.archive, [accepted.package_id], MODELS)
                report = delivery.report
                expected = case['expected']
                self.assertEqual(report.models, tuple(MODELS))
                self.assertEqual(report.positive_count, expected['positive_count'])
                self.assertEqual(report.negative_count, expected['negative_count'])
                self.assertEqual(tuple(str(value) for value in report.auc),
                                 tuple(str(value) for value in expected['auc']))
                self.assertEqual(
                    [(row.ticket, tuple(str(value) for value in row.auc)) for row in report.deletions],
                    [(ticket, tuple(str(value) for value in values))
                     for ticket, values in expected['deletions']])
                self.assertEqual(
                    report.covariance,
                    tuple(tuple(Fraction(0) for _ in MODELS) for _ in MODELS))
                self.assertEqual(read_common_report(self.archive, report.report_id), delivery)
                scenario(f'c5.partner_{name}', package['source'], expected['auc'],
                         [str(value) for value in report.auc], True,
                         read_common_report(self.archive, report.report_id) == delivery,
                         ['handoff/sparse_exchange.py', 'analysis/common_pool.py',
                          'analysis/common_jackknife.py'],
                         f'The {name}-coverage shift changes the common AUC of A and B but not C.')

    def test_two_shifts_cover_different_common_sets(self):
        high = accept_sparse_station(
            self.archive, json.dumps(partner_cases()['high']['package']),
            EvidenceSource(**partner_cases()['high']['package']['source']))
        low = accept_sparse_station(
            self.archive, json.dumps(partner_cases()['low']['package']),
            EvidenceSource(**partner_cases()['low']['package']['source']))
        high_report = issue_common_comparison(self.archive, [high.package_id], MODELS).report
        low_report = issue_common_comparison(self.archive, [low.package_id], MODELS).report
        self.assertEqual(tuple(str(value) for value in high_report.auc), ('1', '1', '1'))
        self.assertEqual(tuple(str(value) for value in low_report.auc), ('0', '0', '1'))
        scenario('c6.coverage_shift', {'shifts': ['high', 'low']},
                 [['1', '1', '1'], ['0', '0', '1']],
                 [[str(value) for value in high_report.auc],
                  [str(value) for value in low_report.auc]],
                 True, high_report.report_id != low_report.report_id,
                 ['analysis/common_selection.py', 'analysis/common_comparison.py'],
                 'Moving the C-covered positive from the high score to the low score flips the A and B AUC.')

    def test_cross_station_covariance_matches_ledger(self):
        rows = (
            ('P', 'p+', 'positive', {'A': 2, 'B': 0}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 2}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
        )
        packages = []
        for station in ('East', 'West'):
            revision = self._seed_sparse(station, rows)
            packages.append(freeze_sparse_station(self.source, self.archive, station, revision).package_id)
        self.source.close()
        forward = issue_common_comparison(self.archive, packages, ['B', 'A'])
        reverse = issue_common_comparison(self.archive, list(reversed(packages)), ['B', 'A'])
        repeated = issue_common_comparison(self.archive, [packages[0], packages[1], packages[0]], ['B', 'A'])
        for delivery in (forward, reverse, repeated):
            report = delivery.report
            self.assertEqual(report.models, ('B', 'A'))
            self.assertEqual((report.positive_count, report.negative_count), (4, 4))
            self.assertEqual(report.auc, (Fraction(1, 2), Fraction(1, 2)))
            self.assertEqual([row.ticket for row in report.deletions], ['P', 'Q'])
            self.assertEqual(report.deletions[0].auc, (Fraction(1), Fraction(0)))
            self.assertEqual(report.deletions[1].auc, (Fraction(0), Fraction(1)))
            self.assertEqual(report.covariance,
                             ((Fraction(1, 4), Fraction(-1, 4)),
                              (Fraction(-1, 4), Fraction(1, 4))))
            self.assertEqual([source.station for source in delivery.sources], ['East', 'West'])
        self.assertEqual(read_common_report(self.archive, forward.report.report_id), forward)
        exported = json.loads(read_common_report(self.archive, forward.report.report_id, as_json=True))
        self.assertEqual(exported['models'], ['B', 'A'])
        quarter = {'numerator': 1, 'denominator': 4}
        negative_quarter = {'numerator': -1, 'denominator': 4}
        self.assertEqual(exported['covariance'], [[quarter, negative_quarter],
                                                  [negative_quarter, quarter]])
        scenario('c7.cross_station_common', {'stations': ['East', 'West']},
                 ['1/2', '1/2'], [str(value) for value in forward.report.auc],
                 packages, [source.package_id for source in forward.sources],
                 ['analysis/common_pool.py', 'analysis/common_jackknife.py',
                  'records/common_retrieval.py'],
                 'Whole-ticket deletion removes the ticket at both stations; covariance keeps the (m-1)/m factor.')

    def test_only_fully_covered_groups_enter_the_common_sample(self):
        rows = (
            ('P', 'p+', 'positive', {'A': 2, 'B': 2}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 0}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'c-only', 'positive', {'C': 9}),
        )
        revision = self._seed_sparse('East', rows)
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        delivery = issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        self.assertEqual((delivery.report.positive_count, delivery.report.negative_count), (2, 2))
        self.assertEqual(delivery.sources[0].package_id, package.package_id)
        with self.assertRaises(InsufficientEvidence):
            issue_common_comparison(self.archive, [package.package_id], ['A', 'B', 'C'])

    def test_missing_class_and_too_few_deletions_are_rejected(self):
        positive_only = (
            ('P', 'p1', 'positive', {'A': 1, 'B': 1}),
            ('Q', 'q1', 'positive', {'A': 1, 'B': 1}),
        )
        revision = self._seed_sparse('East', positive_only)
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        with self.assertRaises(InsufficientEvidence) as caught:
            issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        self.assertIn('both positive and negative', str(caught.exception))

        single_ticket = (
            ('P', 'p+', 'positive', {'A': 1, 'B': 1}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
        )
        revision = self._seed_sparse('West', single_ticket)
        package = freeze_sparse_station(self.source, self.archive, 'West', revision)
        with self.assertRaises(InsufficientEvidence) as caught:
            issue_common_comparison(self.archive, [package.package_id], ['A', 'B'])
        self.assertIn('at least two valid board deletions', str(caught.exception))
        for table in ('common_reports', 'common_report_sources', 'common_report_receipts'):
            self.assertEqual(self.archive.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_invalid_models_and_selections(self):
        rows = (
            ('P', 'p+', 'positive', {'A': 2, 'B': 0}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 2}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
        )
        revision = self._seed_sparse('East', rows)
        package = freeze_sparse_station(self.source, self.archive, 'East', revision)
        for models in (['A'], ['A', 'A'], 'AB', [], (), None, [1, 2]):
            with self.subTest(models=models), self.assertRaises(InvalidInput):
                issue_common_comparison(self.archive, [package.package_id], models)
        for ids in ([], ['sparse-missing'], package.package_id, [package.package_id, 9]):
            with self.subTest(ids=ids), self.assertRaises(InvalidSelection):
                issue_common_comparison(self.archive, ids, ['A', 'B'])
        # V1 packages cannot enter the common flow
        from review import freeze_station
        from review import ModelPair, record_pair
        pair_revision = record_pair(self.source, 'East', 'P', 'pair-occ', 'positive',
                                    ModelPair('A', 'B'), {'A': 1, 'B': 1})
        v1_package = freeze_station(self.source, self.archive, 'East', pair_revision.revision)
        with self.assertRaises(InvalidSelection):
            issue_common_comparison(self.archive, [v1_package.package_id], ['A', 'B'])
        with self.assertRaises(InvalidSelection):
            issue_comparison(self.archive, [package.package_id])
        for table in ('common_reports', 'common_report_sources', 'common_report_receipts'):
            self.assertEqual(self.archive.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_one_package_per_station(self):
        rows = (
            ('P', 'p+', 'positive', {'A': 2, 'B': 0}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 2}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
        )
        first_revision = self._seed_sparse('East', rows)
        first = freeze_sparse_station(self.source, self.archive, 'East', first_revision)
        second_revision = record_sparse_scores(
            self.source, 'East', 'P', 'p+', 'positive', 'correction', {'A': 2, 'B': 2})
        second = freeze_sparse_station(self.source, self.archive, 'East', second_revision)
        with self.assertRaises(InvalidSelection):
            issue_common_comparison(self.archive, [first.package_id, second.package_id], ['A', 'B'])

    def test_filtered_out_station_still_appears_in_sources(self):
        rows = (('P', 'p+', 'positive', {'C': 1}), ('P', 'p-', 'negative', {'C': 1}))
        revision = self._seed_sparse('East', rows)
        c_only = freeze_sparse_station(self.source, self.archive, 'East', revision)
        rows_ab = (
            ('P', 'p+', 'positive', {'A': 2, 'B': 0}),
            ('P', 'p-', 'negative', {'A': 1, 'B': 1}),
            ('Q', 'q+', 'positive', {'A': 0, 'B': 2}),
            ('Q', 'q-', 'negative', {'A': 1, 'B': 1}),
        )
        west_revision = self._seed_sparse('West', rows_ab)
        west = freeze_sparse_station(self.source, self.archive, 'West', west_revision)
        # East contributes no group covering A and B, but stays in the provenance
        delivery = issue_common_comparison(
            self.archive, [c_only.package_id, west.package_id], ['A', 'B'])
        self.assertEqual([source.station for source in delivery.sources], ['East', 'West'])
        self.assertEqual((delivery.report.positive_count, delivery.report.negative_count), (2, 2))
