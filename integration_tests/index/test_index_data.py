# coding=utf-8
"""
Test database methods.

Integration tests: these depend on a local Postgres instance.
"""
from __future__ import absolute_import

import copy
import datetime
import sys
from pathlib import Path
from uuid import UUID

import pytest

from datacube.index._api import Index
from datacube.index.exceptions import DuplicateRecordError, MissingRecordError
from datacube.index.postgres import PostgresDb
from datacube.model import Dataset

_telemetry_uuid = UUID('4ec8fe97-e8b9-11e4-87ff-1040f381a756')
_telemetry_dataset = {
    'product_type': 'satellite_telemetry_data',
    'checksum_path': 'package.sha1',
    'id': str(_telemetry_uuid),
    'ga_label': 'LS8_OLITIRS_STD-MD_P00_LC81160740742015089ASA00_'
                '116_074_20150330T022553Z20150330T022657',

    'ga_level': 'P00',
    'size_bytes': 637660782,
    'platform': {
        'code': 'LANDSAT_8'
    },
    # We're unlikely to have extent info for a raw dataset, we'll use it for search tests.
    'extent': {
        'center_dt': datetime.datetime(2014, 7, 26, 23, 49, 0, 343853).isoformat(),
        'coord': {
            'll': {'lat': -31.33333, 'lon': 149.78434},
            'lr': {'lat': -31.37116, 'lon': 152.20094},
            'ul': {'lat': -29.23394, 'lon': 149.85216},
            'ur': {'lat': -29.26873, 'lon': 152.21782}
        }
    },
    'creation_dt': datetime.datetime(2015, 4, 22, 6, 32, 4).isoformat(),
    'instrument': {'name': 'OLI_TIRS'},
    'format': {
        'name': 'MD'
    },
    'lineage': {
        'source_datasets': {},
        'blah': float('NaN')
    }
}

_pseudo_telemetry_dataset_type = {
    'name': 'ls8_telemetry',
    'description': 'LS8 test',
    'metadata': {
        'product_type': 'satellite_telemetry_data',
        'platform': {
            'code': 'LANDSAT_8'
        },
        'format': {
            'name': 'MD'
        }
    },
    'metadata_type': 'eo'
}
_EXAMPLE_LS7_NBAR_DATASET_FILE = Path(__file__).parent.joinpath('ls7-nbar-example.yaml')


def test_archive_datasets(index, db, local_config, default_metadata_type):
    dataset_type = index.products.add_document(_pseudo_telemetry_dataset_type)
    with db.begin() as transaction:
        was_inserted = transaction.insert_dataset(
            _telemetry_dataset,
            _telemetry_uuid,
            dataset_type.id
        )

    assert was_inserted
    assert index.datasets.has(_telemetry_uuid)

    datsets = index.datasets.search_eager()
    assert len(datsets) == 1

    index.datasets.archive([_telemetry_uuid])
    datsets = index.datasets.search_eager()
    assert len(datsets) == 0

    index.datasets.restore([_telemetry_uuid])
    datsets = index.datasets.search_eager()
    assert len(datsets) == 1


@pytest.fixture
def telemetry_dataset(index, db, default_metadata_type):
    # type: (Index, PostgresDb) -> Dataset
    dataset_type = index.products.add_document(_pseudo_telemetry_dataset_type)
    assert not index.datasets.has(_telemetry_uuid)

    with db.begin() as transaction:
        was_inserted = transaction.insert_dataset(
            _telemetry_dataset,
            _telemetry_uuid,
            dataset_type.id
        )
    assert was_inserted

    return index.datasets.get(_telemetry_uuid)


def test_index_duplicate_dataset(index, db, local_config, default_metadata_type):
    """
    :type index: datacube.index._api.Index
    :type db: datacube.index.postgres._connections.PostgresDb
    """
    dataset_type = index.products.add_document(_pseudo_telemetry_dataset_type)
    assert not index.datasets.has(_telemetry_uuid)

    with db.begin() as transaction:
        was_inserted = transaction.insert_dataset(
            _telemetry_dataset,
            _telemetry_uuid,
            dataset_type.id
        )

    assert was_inserted
    assert index.datasets.has(_telemetry_uuid)

    # Insert again.
    with pytest.raises(DuplicateRecordError):
        with db.connect() as connection:
            was_inserted = connection.insert_dataset(
                _telemetry_dataset,
                _telemetry_uuid,
                dataset_type.id
            )
            assert not was_inserted
    assert index.datasets.has(_telemetry_uuid)


def test_has_dataset(index, telemetry_dataset):
    # type: (Index, Dataset) -> None

    assert index.datasets.has(_telemetry_uuid)
    assert index.datasets.has(str(_telemetry_uuid))

    assert not index.datasets.has(UUID('f226a278-e422-11e6-b501-185e0f80a5c0'))
    assert not index.datasets.has('f226a278-e422-11e6-b501-185e0f80a5c0')


def test_transactions(index, db, local_config, default_metadata_type):
    """
    :type index: datacube.index._api.Index
    :type db: datacube.index.postgres._connections.PostgresDb
    """
    assert not index.datasets.has(_telemetry_uuid)

    dataset_type = index.products.add_document(_pseudo_telemetry_dataset_type)
    with db.begin() as transaction:
        was_inserted = transaction.insert_dataset(
            _telemetry_dataset,
            _telemetry_uuid,
            dataset_type.id
        )
        assert was_inserted
        assert transaction.contains_dataset(_telemetry_uuid)
        # Normal DB uses a separate connection: No dataset visible yet.
        assert not index.datasets.has(_telemetry_uuid)

        transaction.rollback()

    # Should have been rolled back.
    assert not index.datasets.has(_telemetry_uuid)


def test_get_missing_things(index):
    """
    The get(id) methods should return None if the object doesn't exist.

    :type index: datacube.index._api.Index
    """
    uuid_ = UUID('18474b58-c8a6-11e6-a4b3-185e0f80a5c0')
    missing_thing = index.datasets.get(uuid_, include_sources=False)
    assert missing_thing is None, "get() should return none when it doesn't exist"

    missing_thing = index.datasets.get(uuid_, include_sources=True)
    assert missing_thing is None, "get() should return none when it doesn't exist"

    id_ = sys.maxsize
    missing_thing = index.metadata_types.get(id_)
    assert missing_thing is None, "get() should return none when it doesn't exist"

    missing_thing = index.products.get(id_)
    assert missing_thing is None, "get() should return none when it doesn't exist"


def test_index_dataset_with_sources(index, default_metadata_type):
    type_ = index.products.add_document(_pseudo_telemetry_dataset_type)

    parent_doc = _telemetry_dataset.copy()
    parent = Dataset(type_, parent_doc, None, sources={})
    child_doc = _telemetry_dataset.copy()
    child_doc['lineage'] = {'source_datasets': {'source': _telemetry_dataset}}
    child_doc['id'] = '051a003f-5bba-43c7-b5f1-7f1da3ae9cfb'
    child = Dataset(type_, child_doc, local_uri=None, sources={'source': parent})

    with pytest.raises(MissingRecordError):
        index.datasets.add(child, sources_policy='skip')

    index.datasets.add(child, sources_policy='ensure')
    assert index.datasets.get(parent.id)
    assert index.datasets.get(child.id)

    index.datasets.add(child, sources_policy='skip')
    index.datasets.add(child, sources_policy='ensure')
    index.datasets.add(child, sources_policy='verify')
    # Deprecated property, but it should still work until we remove it completely.
    index.datasets.add(child, skip_sources=True)

    parent_doc['platform'] = {'code': 'LANDSAT_9'}
    index.datasets.add(child, sources_policy='ensure')
    index.datasets.add(child, sources_policy='skip')

    with pytest.raises(ValueError):  # TODO: should be DocumentMismatchError
        index.datasets.add(child, sources_policy='verify')


def test_index_dataset_with_location(index, default_metadata_type):
    """
    :type index: datacube.index._api.Index
    :type default_metadata_type: datacube.model.MetadataType
    """
    first_file = Path('/tmp/first/something.yaml').absolute()
    second_file = Path('/tmp/second/something.yaml').absolute()

    type_ = index.products.add_document(_pseudo_telemetry_dataset_type)
    dataset = Dataset(type_, _telemetry_dataset, first_file.as_uri(), sources={})
    index.datasets.add(dataset)
    stored = index.datasets.get(dataset.id)

    assert stored.id == _telemetry_uuid
    # TODO: Dataset types?
    assert stored.type.id == type_.id
    assert stored.metadata_type.id == default_metadata_type.id
    assert stored.local_path == Path(first_file)

    # Ingesting again should have no effect.
    index.datasets.add(dataset)
    stored = index.datasets.get(dataset.id)
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 1
    # Remove the location
    was_removed = index.datasets.remove_location(dataset.id, first_file.as_uri())
    assert was_removed
    was_removed = index.datasets.remove_location(dataset.id, first_file.as_uri())
    assert not was_removed
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 0
    # Re-add the location
    was_added = index.datasets.add_location(dataset.id, first_file.as_uri())
    assert was_added
    was_added = index.datasets.add_location(dataset.id, first_file.as_uri())
    assert not was_added
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 1

    was_archived = index.datasets.archive_location(dataset.id, first_file.as_uri())
    assert was_archived
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 0
    locations = index.datasets.get_archived_locations(dataset.id)
    assert len(locations) == 1
    was_restored = index.datasets.restore_location(dataset.id, first_file.as_uri())
    assert was_restored
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 1

    # Ingesting with a new path should add the second one too.
    dataset.local_uri = second_file.as_uri()
    index.datasets.add(dataset)
    stored = index.datasets.get(dataset.id)
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 2
    # Newest to oldest.
    assert locations == [second_file.as_uri(), first_file.as_uri()]
    # And the second one is newer, so it should be returned as the default local path:
    assert stored.local_path == Path(second_file)

    # Ingestion again without location should have no effect.
    dataset.local_uri = None
    index.datasets.add(dataset)
    stored = index.datasets.get(dataset.id)
    locations = index.datasets.get_locations(dataset.id)
    assert len(locations) == 2
    # Newest to oldest.
    assert locations == [second_file.as_uri(), first_file.as_uri()]
    # And the second one is newer, so it should be returned as the default local path:
    assert stored.local_path == Path(second_file)

    # Ability to get datasets for a location
    # Add a second dataset with a different location (to catch lack of joins, filtering etc)
    second_ds_doc = copy.deepcopy(_telemetry_dataset)
    second_ds_doc['id'] = '366f32d8-e1f8-11e6-94b4-185e0f80a5c0'
    index.datasets.add(Dataset(type_, second_ds_doc, second_file.as_uri(), sources={}))
    dataset_ids = [d.id for d in index.datasets.get_datasets_for_location(first_file.as_uri())]
    assert dataset_ids == [dataset.id]
