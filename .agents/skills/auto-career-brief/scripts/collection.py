"""Validate Codex web research and save new versioned JSON/Markdown files."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

CATEGORIES = {'시장', '고객·상품', '사업·BM', '직무·채용'}


def canonical_url(value):
    p = urlsplit(value)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('유효한 공개 원문 http(s) 주소가 필요합니다.')
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(sorted(query)), ''))


def validate(data):
    result = json.loads(json.dumps(data, ensure_ascii=False))
    as_of = date.fromisoformat(result['as_of'])
    days = result['days']
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError('days는 1~30 정수여야 합니다.')
    mode = result['mode']
    if mode not in ('industry', 'job', 'both'):
        raise ValueError('검색 모드가 올바르지 않습니다.')
    if not result['queries'] or any(not isinstance(q, str) or not q.strip() for q in result['queries']):
        raise ValueError('실제 검색어를 기록하세요.')
    seen = set()
    for row in result['items']:
        for key in ('title', 'source', 'date_evidence', 'relevance'):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f'{key}가 비어 있습니다.')
        if row['source_verified'] is not True or row['my_thought'] != '':
            raise ValueError('본문 확인과 My Thought 빈 값이 필요합니다.')
        if row['category'] not in CATEGORIES:
            raise ValueError('분류가 올바르지 않습니다.')
        if row['search_mode'] not in ('industry', 'job') or (mode != 'both' and row['search_mode'] != mode):
            raise ValueError('자료의 검색 경로가 요청 모드와 다릅니다.')
        if (row['search_mode'] == 'job') != (row['category'] == '직무·채용'):
            raise ValueError('직무 검색은 직무·채용 자료를 반환해야 합니다.')
        if not isinstance(row['company'], list) or any(not isinstance(c, str) for c in row['company']):
            raise ValueError('기업 목록 형식을 확인하세요.')
        if not isinstance(row['summary'], list) or len(row['summary']) != 3 or any(not isinstance(s, str) or not s.strip() for s in row['summary']):
            raise ValueError('사실 요약은 비어 있지 않은 3개 문장이어야 합니다.')
        row['url'] = canonical_url(row['url'])
        if row['url'] in seen:
            raise ValueError('원문 URL이 중복됩니다.')
        seen.add(row['url'])
        published = row['published_date']
        if published is None:
            freshness = 'undated'
        else:
            published = date.fromisoformat(published)
            if published > as_of:
                raise ValueError('미래 발행일은 수집할 수 없습니다.')
            if published >= as_of - timedelta(days=days - 1):
                freshness = 'recent'
            elif published >= as_of - timedelta(days=29):
                freshness = 'expanded'
            elif row['search_mode'] == 'job':
                freshness = 'background'
            else:
                raise ValueError('30일보다 오래된 산업 뉴스입니다.')
        row['freshness'] = freshness
        row['collected_date'] = result['as_of']
    for held in result['held']:
        canonical_url(held['url'])
        if not held['title'].strip() or not held['reason'].strip():
            raise ValueError('보류 제목과 사유를 기록하세요.')
    return result


def markdown(data):
    labels = {'recent': '기본 기간', 'expanded': '30일 내 보충', 'background': '직무 참고', 'undated': '발행일 미확인'}
    start = date.fromisoformat(data['as_of']) - timedelta(days=data['days'] - 1)
    lines = ['# Auto Career Brief 수집 결과', '', f"기준일: {data['as_of']} (한국) · 기본 기간: {start} ~ {data['as_of']} · 모드: {data['mode']}", '',
             '검색·분류·사실 요약 단계입니다. 직무 분석 및 Notion·Slack 전송은 아직 수행하지 않았습니다.', '']
    for key, label in labels.items():
        lines.append(f"- {label}: {sum(r['freshness'] == key for r in data['items'])}건")
    lines.extend([f"- 보류: {len(data['held'])}건", '', '## 실행한 검색어', ''])
    lines.extend('- ' + q for q in data['queries'])
    for i, row in enumerate(data['items'], 1):
        lines.extend(['', f"## {i}. {row['title']}", '', f"{row['category']} · {row['source']} · {labels[row['freshness']]}", '',
                      f"발행일: {row['published_date'] or '미확인'} / 수집일: {row['collected_date']}", '', f"날짜 근거: {row['date_evidence']}", '', '**원문 사실 요약**', ''])
        lines.extend('- ' + s for s in row['summary'])
        lines.extend(['', '**선정 이유 — AI 제안**', '', row['relevance'], '', '**내 생각 — 직접 작성**', '', '____________________', '', f"[원문 보기]({row['url']})"])
    lines.extend(['', '## 보류 자료', ''])
    lines.extend(f"- [{r['title']}]({r['url']}): {r['reason']}" for r in data['held'])
    return '\n'.join(lines) + '\n'


def save(data, output):
    data = validate(data)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    version = 1
    while True:
        stem = f"auto-career-brief-search-{data['as_of']}-{data['mode']}-v{version:02d}"
        jp, mp = output / (stem + '.json'), output / (stem + '.md')
        if not jp.exists() and not mp.exists():
            break
        version += 1
    with jp.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with mp.open('x', encoding='utf-8') as f:
        f.write(markdown(data))
    return jp, mp


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        for path in save(json.loads(args.input.read_text(encoding='utf-8-sig')), args.output):
            print(path.resolve())
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'수집 결과 저장 실패: {error}\n')
