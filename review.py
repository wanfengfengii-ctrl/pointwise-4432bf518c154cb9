import argparse
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.comparison import issue_comparison as issue_comparison
from analysis.common_comparison import issue_common_comparison as issue_common_comparison
from boards.catalog import initialize_boards
from boards.stations import admit_board as admit_board
from boards.tickets import BoardTicket as BoardTicket
from handoff.catalog import StationCatalog as StationCatalog
from handoff.catalog import initialize_handoff
from handoff.evidence import EvidenceSource as EvidenceSource
from handoff.exchange import accept_station as accept_station
from handoff.freeze import freeze_station as freeze_station
from handoff.package import encode_evidence as encode_evidence
from handoff.sparse_catalog import initialize_sparse_handoff
from handoff.sparse_exchange import accept_sparse_station as accept_sparse_station
from handoff.sparse_exchange import read_sparse_station as read_sparse_station
from handoff.sparse_freeze import freeze_sparse_station as freeze_sparse_station
from handoff.sparse_package import encode_sparse_evidence as encode_sparse_evidence
from records.common_publication import initialize_common_records
from records.common_retrieval import read_common_report as read_common_report
from records.publication import initialize_records
from records.retrieval import read_report as read_report
from scoring.intake import record_pair as record_pair
from scoring.ledger import initialize_scoring
from scoring.pairs import ModelPair as ModelPair
from scoring.revisions import Correction as Correction
from scoring.snapshots import read_station_snapshot as read_station_snapshot
from scoring.sparse import initialize_sparse, record_sparse_scores as record_sparse_scores
from storage import connect_database, write_transaction


def open_source(path, *, origin: str | None = None):
    db = connect_database(path)
    try:
        with write_transaction(db):
            initialize_boards(db)
            initialize_scoring(db, origin=origin)
            initialize_sparse(db)
    except BaseException:
        db.close()
        raise
    return db


def open_archive(path):
    db = connect_database(path)
    try:
        with write_transaction(db):
            initialize_handoff(db)
            initialize_sparse_handoff(db)
            initialize_records(db)
            initialize_common_records(db)
    except BaseException:
        db.close()
        raise
    return db


def _sample(name: str):
    return json.loads((Path(__file__).resolve().parent / 'samples' / name).read_text(encoding='utf-8'))


def _freeze_shift(source, archive, shift: dict) -> dict[str, str]:
    models = ModelPair(*shift['models'])
    for board in shift['tickets']:
        ticket = BoardTicket(board['number'], board['entity'])
        for station in board['stations']:
            admit_board(source, ticket, station)
    packages = {}
    for station, measurements in shift['measurements'].items():
        latest = None
        for ticket, occurrence, label, left, right in measurements:
            scores = dict(zip(models.names, (left, right), strict=True))
            latest = record_pair(source, station, ticket, occurrence, label, models, scores)
        if latest is None:
            raise ValueError(f'no sample measurements for {station}')
        packages[station] = freeze_station(source, archive, station, latest.revision).package_id
    return packages


def _numbers(report) -> dict:
    return {
        'auc': [str(value) for value in report.auc],
        'deletions': [[row.ticket, *(str(value) for value in row.auc)] for row in report.deletions],
        'covariance': str(report.covariance),
    }


def _show_comparison(archive, case_id, inputs, ids, expected, expected_ids, oracle, paths):
    delivery = issue_comparison(archive, ids)
    report_id = delivery.report.report_id
    received = read_report(archive, report_id)
    actual = _numbers(delivery.report)
    downstream_expected = {'package_ids': expected_ids, 'complete_receipt': True}
    downstream_actual = {
        'package_ids': [source.package_id for source in received.sources],
        'complete_receipt': received == delivery and received.receipt.report_id == report_id,
    }
    if actual != expected or downstream_actual != downstream_expected:
        raise RuntimeError(f'{case_id}: comparison or its archived receipt disagrees with the hand ledger')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))
    print(read_report(archive, report_id, as_json=True))


def _common_numbers(report) -> dict:
    return {
        'models': list(report.models),
        'positive_count': report.positive_count,
        'negative_count': report.negative_count,
        'auc': [str(value) for value in report.auc],
        'deletions': [[row.ticket, *[str(value) for value in row.auc]] for row in report.deletions],
        'covariance': [[str(value) for value in line] for line in report.covariance],
    }


def _print_common_scenario(case_id, inputs, expected, delivery, paths, oracle):
    actual = _common_numbers(delivery.report)
    if actual != expected:
        raise RuntimeError(f'{case_id}: common comparison disagrees with the hand ledger')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': {
            'package_ids': [source.package_id for source in delivery.sources],
            'receipt_id': delivery.receipt.receipt_id,
        },
        'code_paths': paths,
        'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


def _run_common_demo(archive, root) -> None:
    from common_support_examples import MODELS, partner_cases

    cases = partner_cases()
    accepted = {}
    for name in ('high', 'low'):
        package = cases[name]['package']
        accepted[name] = accept_sparse_station(
            archive, json.dumps(package), EvidenceSource(**package['source']))
    deliveries = {}
    for name in ('high', 'low'):
        expected = cases[name]['expected']
        delivery = issue_common_comparison(archive, [accepted[name].package_id], MODELS)
        deliveries[name] = delivery
        _print_common_scenario(
            f'c10.partner_{name}_coverage',
            {'package_id': accepted[name].package_id, 'models': list(MODELS)},
            {
                'models': list(MODELS),
                'positive_count': expected['positive_count'],
                'negative_count': expected['negative_count'],
                'auc': [str(value) for value in expected['auc']],
                'deletions': [[ticket, *[str(value) for value in values]]
                              for ticket, values in expected['deletions']],
                'covariance': [[str(value) for value in line] for line in expected['covariance']],
            },
            delivery,
            ['handoff/sparse_exchange.py', 'analysis/common_pool.py',
             'analysis/common_jackknife.py', 'records/common_publication.py'],
            'Two partner shifts share P and Q; moving the C-covered positive flips the A and B AUC from 1 to 0.',
        )
    print('SPARSE_COVERAGE_SHIFT ' + json.dumps({
        'high_auc': [str(value) for value in deliveries['high'].report.auc],
        'low_auc': [str(value) for value in deliveries['low'].report.auc],
    }, sort_keys=True))

    # Local sparse source: two stations, shared tickets, then the source database is closed.
    sparse_path = root / 'sparse-source.sqlite3'
    with closing(open_source(sparse_path, origin='night-center')) as sparse_source:
        for station in ('East', 'West'):
            for ticket in ('P', 'Q'):
                admit_board(sparse_source, BoardTicket(ticket, f'film-{ticket}'), station)
        local_rows = {
            'East': [
                ('P', 'east-p+', 'positive', {'A': 2, 'B': 0}),
                ('P', 'east-p-', 'negative', {'A': 1, 'B': 1}),
                ('Q', 'east-q+', 'positive', {'A': 0, 'B': 2}),
                ('Q', 'east-q-', 'negative', {'A': 1, 'B': 1}),
            ],
            'West': [
                ('P', 'west-p+', 'positive', {'A': 2, 'B': 0}),
                ('P', 'west-p-', 'negative', {'A': 1, 'B': 1}),
                ('Q', 'west-q+', 'positive', {'A': 0, 'B': 2}),
                ('Q', 'west-q-', 'negative', {'A': 1, 'B': 1}),
            ],
        }
        package_ids = []
        for station in ('East', 'West'):
            revision = None
            for index, (ticket, occurrence, label, scores) in enumerate(local_rows[station]):
                revision = record_sparse_scores(
                    sparse_source, station, ticket, occurrence, label, f'{station}-{index}', scores)
            fixed = freeze_sparse_station(sparse_source, archive, station, revision)
            package_ids.append(fixed.package_id)
    print('SPARSE_SOURCE_CLOSED ' + json.dumps({'source': str(sparse_path), 'open': False}))

    delivery = issue_common_comparison(archive, package_ids, ['A', 'B'])
    expected = {
        'models': ['A', 'B'],
        'positive_count': 4,
        'negative_count': 4,
        'auc': ['1/2', '1/2'],
        'deletions': [['P', '0', '1'], ['Q', '1', '0']],
        'covariance': [['1/4', '-1/4'], ['-1/4', '1/4']],
    }
    _print_common_scenario(
        'c11.offline_cross_station',
        {'source_open': False, 'package_ids': package_ids, 'models': ['A', 'B']},
        expected, delivery,
        ['handoff/sparse_freeze.py', 'analysis/common_selection.py',
         'analysis/common_jackknife.py', 'records/common_retrieval.py'],
        'After the source closes, the archive still pools both stations, deletes whole tickets and signs one report.',
    )
    print(read_common_report(archive, delivery.report.report_id, as_json=True))
    return delivery


def run_demo() -> None:
    shift = _sample('shift.json')
    manual = _sample('manual-ledger.json')
    partner = _sample('foreign-stations.json')['reverse']
    with TemporaryDirectory(prefix='film-review-') as directory:
        root = Path(directory)
        with closing(open_archive(root / 'archive.sqlite3')) as archive:
            with closing(open_source(root / 'source.sqlite3', origin=shift['origin'])) as source:
                ids = _freeze_shift(source, archive, shift)
            _show_comparison(
                archive, 'v6.reversed_selection',
                {'measurements': shift['measurements'], 'station_order': ['West', 'East']},
                [ids['West'], ids['East']], manual['cross_station'], [ids['East'], ids['West']],
                manual['oracles']['cross_station'],
                ['handoff/freeze.py', 'analysis/pool.py', 'analysis/jackknife.py', 'records/retrieval.py'],
            )
            imported = accept_station(archive, json.dumps(partner), EvidenceSource(**partner['source']))
            _show_comparison(
                archive, 'v5.aligned_pairs', partner, [imported.package_id], manual['reverse'],
                [partner['package_id']], manual['oracles']['reverse'],
                ['handoff/exchange.py', 'analysis/jackknife.py', 'records/publication.py', 'records/retrieval.py'],
            )
            offline_delivery = _run_common_demo(archive, root)

        # Reopen a closed archive and claim the stored common report by its id.
        with closing(open_archive(root / 'archive.sqlite3')) as reopened:
            claimed = read_common_report(reopened, offline_delivery.report.report_id)
            assert claimed == offline_delivery
            print('SPARSE_REOPEN_CLAIM ' + json.dumps({
                'report_id': offline_delivery.report.report_id,
                'receipt_id': claimed.receipt.receipt_id,
                'package_ids': [source.package_id for source in claimed.sources],
                'numbers': _common_numbers(claimed.report),
            }, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description='Paired film inspection review')
    parser.add_argument('command', choices=['demo'])
    parser.parse_args()
    run_demo()


if __name__ == '__main__':
    main()
