"""Join Codex-authored career insights to verified research without changing source facts."""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from collection import validate as validate_collection, canonical_url

FIELDS = {'url', 'what_changed', 'business_view', 'product_view', 'kpis', 'career_uses', 'questions', 'action', 'limitations'}


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('분석의 필수 항목이 비어 있습니다.')


def array(value):
    if not isinstance(value, list) or not value:
        raise ValueError('하나 이상의 항목이 필요합니다.')


def combine(collection, analyses):
    result = validate_collection(collection)
    if not isinstance(analyses, dict) or set(analyses) != {'analyses'} or not isinstance(analyses['analyses'], list):
        raise ValueError('analyses 배열이 필요합니다.')
    lookup = {}
    for original in analyses['analyses']:
        row = json.loads(json.dumps(original, ensure_ascii=False))
        if set(row) != FIELDS:
            raise ValueError('분석 필드를 확인하세요. 원문이나 My Thought는 수정할 수 없습니다.')
        url = canonical_url(row.pop('url'))
        if url in lookup:
            raise ValueError('같은 원문에 분석이 중복되었습니다.')
        for field in ('what_changed', 'business_view', 'product_view'):
            block = row[field]
            if not isinstance(block, dict) or set(block) != {'text', 'fact_refs'}:
                raise ValueError('관점마다 본문과 근거 번호가 필요합니다.')
            text(block['text'])
            array(block['fact_refs'])
            if any(type(n) is not int or not 1 <= n <= 3 for n in block['fact_refs']):
                raise ValueError('근거는 사실 요약 1~3번을 참조해야 합니다.')
        for field in ('kpis', 'career_uses', 'questions', 'limitations'):
            array(row[field])
        for kpi in row['kpis']:
            if not isinstance(kpi, dict) or set(kpi) != {'name', 'definition', 'why', 'data_source', 'availability'}:
                raise ValueError('데이터 제안 형식이 올바르지 않습니다.')
            for value in kpi.values():
                text(value)
            if kpi['availability'] not in ('공개 자료 확인', '공개 여부 미확인', '내부 데이터 필요'):
                raise ValueError('데이터 접근 가능성을 표시하세요.')
        for use in row['career_uses']:
            if not isinstance(use, dict) or set(use) != {'type', 'how'} or use['type'] not in ('면접', '자소서', '포트폴리오'):
                raise ValueError('취업 활용 구분이 올바르지 않습니다.')
            text(use['how'])
        for value in row['questions'] + row['limitations']:
            text(value)
        action = row['action']
        if not isinstance(action, dict) or set(action) != {'task', 'deliverable', 'minutes'}:
            raise ValueError('작업·산출물·시간을 명시하세요.')
        text(action['task'])
        text(action['deliverable'])
        if type(action['minutes']) is not int or not 10 <= action['minutes'] <= 60:
            raise ValueError('실습 시간은 10~60분입니다.')
        lookup[url] = row
    expected = {item['url'] for item in result['items']}
    if expected != set(lookup):
        raise ValueError('수집 자료와 분석 URL이 일치하지 않습니다. 누락·미등록·보류 자료를 확인하세요.')
    for item in result['items']:
        item['career_insight'] = lookup[item['url']]
    return result


def render(data):
    end = date.fromisoformat(data['as_of'])
    start = end - timedelta(days=data['days'] - 1)
    supplement = (f"{end - timedelta(days=29)} ~ {start - timedelta(days=1)}" if data['days'] < 30 else '없음')
    labels = {'recent': '최신 자료', 'expanded': '보충 자료', 'background': '오래된 직무 참고', 'undated': '발행일 미확인'}
    lines = ['# Auto Career Brief 커리어 인사이트', '',
             f"수집 기준일: {end} · 분석 생성: {data['generated_at']}", '',
             f'최신 자료: {start} ~ {end} / 보충 자료: {supplement} (발행일 기준, 양 끝 날짜 포함)', '',
             '기존 수집 자료에 분석을 추가했습니다. 새로운 뉴스 수집이나 Notion·Slack 전송 결과가 아닙니다.', '',
             '관점·데이터·취업 활용·질문·실습은 AI 제안입니다. 근거 번호는 아래 원문 사실 요약의 번호입니다.', '']
    for item in data['items']:
        insight = item['career_insight']
        lines.extend([f"## {item['title']}", '', f"{item['category']} · {labels[item['freshness']]} · 발행일 {item['published_date'] or '미확인'}", '',
                      f"[원문 — {item['source']}]({item['url']})", '', '### 원문 사실 요약', ''])
        lines.extend(f'{i}. {s}' for i, s in enumerate(item['summary'], 1))
        for field, label in [('what_changed', '무엇이 달라졌는가'), ('business_view', '사업기획 관점'), ('product_view', '상품기획 관점')]:
            block = insight[field]
            refs = ', '.join(str(n) for n in block['fact_refs'])
            lines.extend(['', f'### {label} — AI 분석', '', block['text'], '', f'연결 근거: 사실 {refs}번'])
        lines.extend(['', '### 확인할 데이터와 KPI — AI 제안', ''])
        for kpi in insight['kpis']:
            lines.extend([f"- **{kpi['name']}**: {kpi['definition']}", f"  - 필요한 이유: {kpi['why']}", f"  - 확인할 곳: {kpi['data_source']} / {kpi['availability']}"])
        lines.extend(['', '### 취업 활용 — AI 제안', ''])
        lines.extend(f"- {u['type']}: {u['how']}" for u in insight['career_uses'])
        lines.extend(['', '### 생각해볼 질문', ''])
        lines.extend('- ' + q for q in insight['questions'])
        a = insight['action']
        lines.extend(['', f"### 작은 실습 — 약 {a['minutes']}분", '', a['task'], '', f"만들 결과: {a['deliverable']}", '', '### 아직 알 수 없는 점', ''])
        lines.extend('- ' + x for x in insight['limitations'])
        lines.extend(['', '### 내 생각 — 직접 작성', '', '____________________', ''])
    lines.extend(['## 보류 자료 — 분석 제외', ''])
    lines.extend(f"- [{r['title']}]({r['url']}): {r['reason']}" for r in data['held'])
    lines.extend(['', '## 원본 연결', '', f"입력 파일: {data['source_collection']}", '', f"SHA-256: {data['source_collection_sha256']}"])
    return '\n'.join(lines) + '\n'


def save(collection_path, analyses_path, output):
    raw = Path(collection_path).read_bytes()
    data = combine(json.loads(raw.decode('utf-8-sig')), json.loads(Path(analyses_path).read_text(encoding='utf-8-sig')))
    data.update(source_collection=Path(collection_path).name, source_collection_sha256=hashlib.sha256(raw).hexdigest(),
                generated_at=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    version = 1
    while True:
        stem = f"auto-career-brief-insight-{data['as_of']}-{data['mode']}-v{version:02d}"
        jp, mp = output / (stem + '.json'), output / (stem + '.md')
        if not jp.exists() and not mp.exists():
            break
        version += 1
    rendered = render(data)
    with jp.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with mp.open('x', encoding='utf-8') as f:
        f.write(rendered)
    return jp, mp


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('analyses', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        for path in save(args.collection, args.analyses, args.output):
            print(path.resolve())
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'인사이트 저장 실패: {error}\n')
