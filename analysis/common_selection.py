"""Selection rules for the common-support multi-model comparison."""

from collections.abc import Iterable
from dataclasses import dataclass

from handoff.catalog import StationCatalog
from handoff.sparse_catalog import SparseStationCatalog
from handoff.sparse_evidence import SparseStationEvidence
from storage import InvalidInput, InvalidSelection, MissingItem, identifier


@dataclass(frozen=True)
class CommonSelection:
    packages: tuple[SparseStationEvidence, ...]
    models: tuple[str, ...]


def _validate_models(models: object) -> tuple[str, ...]:
    if not isinstance(models, (list, tuple)):
        raise InvalidInput('models must be an ordered list or tuple of model names')
    if len(models) < 2:
        raise InvalidInput('select at least two distinct models')
    ordered = tuple(identifier(model, 'model name') for model in models)
    if len(set(ordered)) != len(ordered):
        raise InvalidInput('the requested models must be distinct')
    return ordered


def select_common(
    db, package_ids: Iterable[str], models: Iterable[str]
) -> CommonSelection:
    ordered_models = _validate_models(models)
    if not isinstance(package_ids, Iterable) or isinstance(package_ids, (str, bytes, bytearray)):
        raise InvalidSelection('provide a collection of sparse station package ids')
    try:
        unique_ids = {identifier(package_id, 'package id') for package_id in package_ids}
    except InvalidInput as exc:
        raise InvalidSelection(str(exc)) from exc
    if not unique_ids:
        raise InvalidSelection('select at least one sparse station package')

    sparse_catalog = SparseStationCatalog(db)
    v1_catalog = StationCatalog(db)
    packages: list[SparseStationEvidence] = []
    stations = set()
    for package_id in sorted(unique_ids):
        try:
            v1_catalog.read(package_id)
        except MissingItem:
            pass
        else:
            raise InvalidSelection(f'package {package_id!r} is a V1 station package')
        try:
            package = sparse_catalog.read(package_id)
        except MissingItem as exc:
            raise InvalidSelection(str(exc)) from exc
        station = package.source.station
        if station in stations:
            raise InvalidSelection(f'more than one package selected for station {station!r}')
        stations.add(station)
        packages.append(package)

    packages.sort(key=lambda package: package.source.station)
    return CommonSelection(tuple(packages), ordered_models)
