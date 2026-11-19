"""Build the common sample pool from selected sparse station packages."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from analysis.common_selection import CommonSelection
from handoff.sparse_evidence import SparseContribution, SparseStationEvidence


# Per model: positive histogram and negative histogram over the retained common sample.
ModelHistograms = tuple[Counter, Counter]


@dataclass(frozen=True)
class CommonRecord:
    station: str
    ticket: str
    label: str
    contribution: SparseContribution


@dataclass(frozen=True)
class CommonPool:
    models: tuple[str, ...]
    packages: tuple[SparseStationEvidence, ...]
    records: tuple[CommonRecord, ...]
    tickets: tuple[str, ...]


def build_common_pool(selection: CommonSelection) -> CommonPool:
    requested = set(selection.models)
    records: list[CommonRecord] = []
    for package in selection.packages:
        for contribution in package.contributions:
            if requested.issubset(contribution.scores):
                records.append(CommonRecord(
                    package.source.station, contribution.ticket, contribution.label, contribution
                ))
    tickets = tuple(sorted({record.ticket for record in records}))
    return CommonPool(selection.models, selection.packages, tuple(records), tickets)


def histograms(records: Iterable[CommonRecord], models: tuple[str, ...]) -> tuple[ModelHistograms, ...]:
    result: tuple[list[Counter], ...] = tuple((Counter(), Counter()) for _ in models)
    for record in records:
        label_index = 0 if record.label == 'positive' else 1
        for index, model in enumerate(models):
            for score, multiplicity in record.contribution.scores[model]:
                result[index][label_index][score] += multiplicity
    return result
