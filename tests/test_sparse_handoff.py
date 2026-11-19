import copy
import json

from handoff.evidence import EvidenceSource
from handoff.sparse_package import decode_sparse_evidence, encode_sparse_evidence
from review import accept_sparse_station, read_sparse_station
from storage import InvalidEvidence, MissingItem
from tests.support import ReviewTest, scenario


def sparse_document():
    return {
        'version': 2,
        'package_id': 'partner-sparse-1',
        'source': {'origin': 'partner-lab', 'station': 'Partner', 'revision': 'B1'},
        'contributions': [
            {'ticket': 'P', 'label': 'positive', 'count': 2,
             'scores': {'A': [['2', 2]], 'B': [['0', 1], ['2', 1]]}},
            {'ticket': 'P', 'label': 'negative', 'count': 1,
             'scores': {'A': [['1', 1]], 'B': [['1', 1]]}},
            {'ticket': 'Q', 'label': 'positive', 'count': 1,
             'scores': {'C': [['2', 1]]}},
        ],
    }


class SparseHandoffTests(ReviewTest):
    def test_accept_and_replay_equivalent_sparse_package(self):
        document = sparse_document()
        source = EvidenceSource(**document['source'])
        accepted = accept_sparse_station(self.archive, json.dumps(document), source)
        self.assertEqual(read_sparse_station(self.archive, document['package_id']), accepted)
        self.assertEqual(decode_sparse_evidence(encode_sparse_evidence(accepted)), accepted)

        shuffled = copy.deepcopy(document)
        shuffled['contributions'].reverse()
        positive_group = next(group for group in shuffled['contributions']
                              if group['ticket'] == 'P' and group['label'] == 'positive')
        positive_group['scores'] = {
            name: positive_group['scores'][name]
            for name in reversed(list(positive_group['scores']))
        }
        negative_group = next(group for group in shuffled['contributions']
                              if group['ticket'] == 'P' and group['label'] == 'negative')
        negative_group['scores']['B'][0][0] = '1/1'
        replayed = accept_sparse_station(self.archive, json.dumps(shuffled), source)
        self.assertEqual(replayed, accepted)
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 1)
        scenario('c4.sparse_equivalent_replay', {'package_id': document['package_id']},
                 accepted.package_id, replayed.package_id, True, replayed == accepted,
                 ['handoff/sparse_package.py', 'handoff/sparse_catalog.py'],
                 'Group, model, column order and rational spelling are irrelevant for equivalence.')

    def test_declared_source_must_match(self):
        document = sparse_document()
        with self.assertRaises(InvalidEvidence) as caught:
            accept_sparse_station(
                self.archive, json.dumps(document),
                EvidenceSource('wrong-lab', document['source']['station'], document['source']['revision']))
        self.assertEqual(caught.exception.code, 'INVALID_STATION_EVIDENCE')
        with self.assertRaises(MissingItem):
            read_sparse_station(self.archive, document['package_id'])
        accepted = accept_sparse_station(
            self.archive, json.dumps(document), EvidenceSource(**document['source']))
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 1)
        self.assertEqual(read_sparse_station(self.archive, accepted.package_id), accepted)

    def test_invalid_documents_leave_no_trace(self):
        base = sparse_document()
        invalid_documents = []
        for version in (1, 3, '2', True):
            document = copy.deepcopy(base)
            document['version'] = version
            invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'][0]['count'] = 0
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'][0]['count'] = True
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'][0]['scores']['A'][0][1] = 3
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        del document['source']['station']
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'].append(copy.deepcopy(document['contributions'][0]))
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'][0]['scores']['A'].append(['2', 1])
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'][0]['scores']['D'] = []
        invalid_documents.append(document)
        document = copy.deepcopy(base)
        document['contributions'] = []
        invalid_documents.append(document)
        # duplicated top-level JSON field
        invalid_documents.append(json.dumps(base)[:-1] + ',"version":2}')
        for document in invalid_documents:
            payload = document if isinstance(document, str) else json.dumps(document)
            with self.subTest(payload=payload[:60]), self.assertRaises(InvalidEvidence):
                accept_sparse_station(self.archive, payload, EvidenceSource(**base['source']))
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 0)

    def test_package_id_and_source_triplet_collisions(self):
        document = sparse_document()
        source = EvidenceSource(**document['source'])
        accepted = accept_sparse_station(self.archive, json.dumps(document), source)

        changed = copy.deepcopy(document)
        changed['contributions'][0]['scores']['A'][0][0] = '999'
        changed['package_id'] = 'another-id'
        with self.assertRaises(InvalidEvidence):
            accept_sparse_station(self.archive, json.dumps(changed), source)

        stolen = copy.deepcopy(document)
        stolen['contributions'][0]['scores']['A'][0][0] = '999'
        with self.assertRaises(InvalidEvidence):
            accept_sparse_station(self.archive, json.dumps(stolen), source)
        self.assertEqual(read_sparse_station(self.archive, accepted.package_id), accepted)

        second_revision = copy.deepcopy(document)
        second_revision['source']['revision'] = 'B2'
        second_revision['package_id'] = 'partner-sparse-2'
        second = accept_sparse_station(
            self.archive, json.dumps(second_revision), EvidenceSource(**second_revision['source']))
        self.assertNotEqual(second.package_id, accepted.package_id)
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM sparse_station_packages').fetchone()[0], 2)

    def test_unknown_sparse_package_is_missing(self):
        with self.assertRaises(MissingItem):
            read_sparse_station(self.archive, 'sparse-absent')
