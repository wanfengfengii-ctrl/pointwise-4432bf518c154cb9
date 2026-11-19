"""Retrieval and JSON export of fixed common-support reports."""

from dataclasses import dataclass
import json

from records.common_provenance import read_common_sources
from records.common_publication import CommonReport, read_common_snapshot
from records.common_receipts import read_common_receipt
from records.export import format_fraction
from records.provenance import ReportSource
from records.receipts import ReportReceipt


@dataclass(frozen=True)
class CommonReportDelivery:
    report: CommonReport
    sources: tuple[ReportSource, ...]
    receipt: ReportReceipt


def export_common_report(delivery: CommonReportDelivery) -> str:
    report = delivery.report
    payload = {
        'report_id': report.report_id,
        'models': list(report.models),
        'positive_count': report.positive_count,
        'negative_count': report.negative_count,
        'auc': [format_fraction(value) for value in report.auc],
        'deletions': [
            {'ticket': row.ticket, 'auc': [format_fraction(value) for value in row.auc]}
            for row in report.deletions
        ],
        'covariance': [[format_fraction(value) for value in line] for line in report.covariance],
        'sources': [
            {
                'package_id': source.package_id,
                'station': source.station,
                'origin': source.origin,
                'revision': source.revision,
            }
            for source in delivery.sources
        ],
        'receipt': {'report_id': delivery.receipt.report_id, 'receipt_id': delivery.receipt.receipt_id},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def read_common_report(
    db, report_id: int, *, as_json: bool = False
) -> CommonReportDelivery | str:
    report = read_common_snapshot(db, report_id)
    sources = read_common_sources(db, report_id)
    receipt = read_common_receipt(db, report_id)
    delivery = CommonReportDelivery(report, sources, receipt)
    if as_json:
        return export_common_report(delivery)
    return delivery
