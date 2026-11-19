"""Whole-ticket deletions and covariance for the common multi-model sample."""

from dataclasses import dataclass
from fractions import Fraction

from analysis.auc import auc
from analysis.common_pool import CommonPool, histograms
from storage import InsufficientEvidence


@dataclass(frozen=True)
class CommonDeletion:
    ticket: str
    auc: tuple[Fraction, ...]


@dataclass(frozen=True)
class CommonDeletionResult:
    full_auc: tuple[Fraction, ...]
    positive_count: int
    negative_count: int
    deletions: tuple[CommonDeletion, ...]
    covariance: tuple[tuple[Fraction, ...], ...]


def _column_auc(pool_histograms, index: int) -> Fraction:
    positive, negative = pool_histograms[index]
    return auc(positive, negative)


def evaluate_common(pool: CommonPool) -> CommonDeletionResult:
    full = histograms(pool.records, pool.models)
    for positive, negative in full:
        if not positive or not negative:
            raise InsufficientEvidence('AUC requires both positive and negative measurements')
    full_auc = tuple(_column_auc(full, index) for index in range(len(pool.models)))
    positive_count = sum(full[0][0].values())
    negative_count = sum(full[0][1].values())

    deletions: list[CommonDeletion] = []
    for ticket in pool.tickets:
        remaining = tuple(record for record in pool.records if record.ticket != ticket)
        remaining_histograms = histograms(remaining, pool.models)
        if any(not positive or not negative for positive, negative in remaining_histograms):
            continue
        deletions.append(CommonDeletion(
            ticket,
            tuple(_column_auc(remaining_histograms, index) for index in range(len(pool.models))),
        ))

    m = len(deletions)
    if m < 2:
        raise InsufficientEvidence('comparison requires at least two valid board deletions')

    dimension = len(pool.models)
    means = tuple(
        sum(row.auc[index] for row in deletions) / m for index in range(dimension)
    )
    matrix = []
    for i in range(dimension):
        line = []
        for j in range(dimension):
            cross_products = sum(
                (row.auc[i] - means[i]) * (row.auc[j] - means[j]) for row in deletions
            )
            line.append(Fraction(m - 1, m) * cross_products)
        matrix.append(tuple(line))
    return CommonDeletionResult(
        full_auc, positive_count, negative_count, tuple(deletions), tuple(matrix)
    )
