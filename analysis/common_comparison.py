"""Issue a common-support comparison over selected sparse station packages."""

from collections.abc import Iterable
import sqlite3

from analysis.common_jackknife import evaluate_common
from analysis.common_pool import build_common_pool
from analysis.common_selection import select_common
from records.common_publication import publish_common_report
from records.common_retrieval import CommonReportDelivery
from records.provenance import ReportSource


def issue_common_comparison(
    db: sqlite3.Connection, package_ids: Iterable[str], models: Iterable[str]
) -> CommonReportDelivery:
    selection = select_common(db, package_ids, models)
    pool = build_common_pool(selection)
    result = evaluate_common(pool)
    sources = tuple(
        ReportSource(package.package_id, package.source.station, package.source.origin,
                     package.source.revision)
        for package in selection.packages
    )
    report, receipt = publish_common_report(db, selection.models, result, sources)
    return CommonReportDelivery(report, sources, receipt)
