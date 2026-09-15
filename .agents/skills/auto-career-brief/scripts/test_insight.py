import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_collection import sample
from insight import combine, save


def analysis():
    block = {'text': '검증용 분석 제안', 'fact_refs': [1]}
    return {'analyses': [{
        'url': sample()['items'][0]['url'],
        'what_changed': copy.deepcopy(block), 'business_view': copy.deepcopy(block), 'product_view': copy.deepcopy(block),
        'kpis': [{'name': '판매량', 'definition': '기간 내 판매 대수', 'why': '규모 확인', 'data_source': '발행처', 'availability': '공개 여부 미확인'}],
        'career_uses': [{'type': '포트폴리오', 'how': '비교표 만들기'}],
        'questions': ['비교 기준은 무엇인가?'], 'limitations': ['원인은 미확인'],
        'action': {'task': '자료 비교', 'deliverable': '비교표', 'minutes': 20}}]}


class InsightTests(unittest.TestCase):
    def test_source_and_thought_preserved(self):
        data = sample()
        original = copy.deepcopy(data)
        result = combine(data, analysis())
        self.assertEqual(data, original)
        for key in ('summary', 'published_date', 'source', 'my_thought', 'date_evidence'):
            self.assertEqual(result['items'][0][key], original['items'][0][key])

    def test_missing_unknown_and_duplicate_rejected(self):
        cases = [{'analyses': []}, analysis(), analysis()]
        cases[1]['analyses'][0]['url'] = 'https://example.com/unknown'
        cases[2]['analyses'] *= 2
        for case in cases:
            with self.assertRaises(ValueError):
                combine(sample(), case)

    def test_invalid_refs_rejected(self):
        for refs in ([], [0], [4], [True], ['1']):
            data = analysis()
            data['analyses'][0]['business_view']['fact_refs'] = refs
            with self.assertRaises(ValueError):
                combine(sample(), data)

    def test_unverified_and_source_overwrite_rejected(self):
        source = sample()
        source['items'][0]['source_verified'] = False
        with self.assertRaises(ValueError):
            combine(source, analysis())
        for field in ('my_thought', 'summary'):
            data = analysis()
            data['analyses'][0][field] = '무단 변경'
            with self.assertRaises(ValueError):
                combine(sample(), data)

    def test_missing_kpi_and_unbounded_action_rejected(self):
        data = analysis()
        data['analyses'][0]['kpis'][0]['definition'] = ''
        with self.assertRaises(ValueError):
            combine(sample(), data)
        data = analysis()
        data['analyses'][0]['action']['minutes'] = 120
        with self.assertRaises(ValueError):
            combine(sample(), data)

    def test_save_versions_and_provenance(self):
        with tempfile.TemporaryDirectory(prefix='auto-career-insight-test-') as folder:
            root = Path(folder)
            cp, ap = root / 'collection.json', root / 'analysis.json'
            cp.write_text(json.dumps(sample()), encoding='utf-8')
            ap.write_text(json.dumps(analysis()), encoding='utf-8')
            before = cp.read_bytes()
            one = save(cp, ap, root)
            saved = [p.read_bytes() for p in one]
            two = save(cp, ap, root)
            self.assertNotEqual(one, two)
            self.assertEqual(saved, [p.read_bytes() for p in one])
            self.assertEqual(before, cp.read_bytes())
            result = json.loads(one[0].read_text(encoding='utf-8'))
            self.assertEqual(len(result['source_collection_sha256']), 64)
            self.assertEqual(result['items'][0]['my_thought'], '')
            md = one[1].read_text(encoding='utf-8')
            self.assertIn('2026-08-17 ~ 2026-09-08', md)


if __name__ == '__main__':
    unittest.main()
