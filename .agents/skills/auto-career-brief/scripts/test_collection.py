import copy
from pathlib import Path
import tempfile
import unittest
from collection import validate, save, canonical_url


def sample():
    return {'as_of': '2026-09-15', 'days': 7, 'mode': 'both', 'queries': ['자동차 판매'], 'held': [], 'items': [{
        'title': '검사용 자료', 'source': '검사용 발행처', 'url': 'https://example.com/news?id=1',
        'published_date': '2026-09-09', 'date_evidence': '원문 날짜', 'category': '시장',
        'search_mode': 'industry', 'company': [], 'summary': ['사실 A', '사실 B', '사실 C'],
        'relevance': '검사용 선정 이유', 'my_thought': '', 'source_verified': True}]}


class CollectionTests(unittest.TestCase):
    def test_date_boundaries(self):
        for published, expected in [('2026-09-15', 'recent'), ('2026-09-09', 'recent'), ('2026-09-08', 'expanded'), ('2026-08-17', 'expanded'), (None, 'undated')]:
            data = sample()
            data['items'][0]['published_date'] = published
            self.assertEqual(validate(data)['items'][0]['freshness'], expected)
        for published in ['2026-09-16', '2026-08-16']:
            data = sample()
            data['items'][0]['published_date'] = published
            with self.assertRaises(ValueError):
                validate(data)

    def test_old_job_is_background(self):
        data = sample()
        data['mode'] = 'job'
        data['items'][0].update(search_mode='job', category='직무·채용', published_date='2023-01-01')
        self.assertEqual(validate(data)['items'][0]['freshness'], 'background')

    def test_tracking_duplicate_rejected_and_job_ids_preserved(self):
        data = sample()
        other = copy.deepcopy(data['items'][0])
        other['url'] += '&utm_source=mail#intro'
        data['items'].append(other)
        with self.assertRaises(ValueError):
            validate(data)
        self.assertNotEqual(canonical_url('https://example.com/job?id=1'), canonical_url('https://example.com/job?id=2'))

    def test_missing_evidence_or_user_thought_rejected(self):
        for update in [{'source_verified': False}, {'my_thought': 'AI가 대신 작성'}, {'summary': ['한 줄']}, {'category': '기타'}]:
            data = sample()
            data['items'][0].update(update)
            with self.assertRaises(ValueError):
                validate(data)

    def test_modes_and_empty_results(self):
        data = sample()
        data['mode'] = 'job'
        with self.assertRaises(ValueError):
            validate(data)
        data['items'] = []
        self.assertEqual(validate(data)['items'], [])

    def test_existing_outputs_preserved(self):
        with tempfile.TemporaryDirectory(prefix='auto-career-brief-test-') as folder:
            first = save(sample(), folder)
            previous = [p.read_bytes() for p in first]
            second = save(sample(), folder)
            self.assertNotEqual(first, second)
            self.assertEqual(previous, [p.read_bytes() for p in first])
            self.assertEqual(len(list(Path(folder).iterdir())), 4)


if __name__ == '__main__':
    unittest.main()
