"""Validate decision-focused insights while preserving original research."""
import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import insight

def strings(obj, fields):
    if not isinstance(obj, dict) or set(obj) != set(fields):
        raise ValueError('기획 필수 항목을 확인하세요: ' + ', '.join(fields))
    for value in obj.values():
        insight.text(value)

def combine(collection, analyses):
    if not isinstance(analyses, dict) or set(analyses) != {'schema_version', 'analyses'} or type(analyses['schema_version']) is not int or analyses['schema_version'] != 2:
        raise ValueError('새 기획 분석은 schema_version 2가 필요합니다.')
    legacy = copy.deepcopy(analyses)
    legacy.pop('schema_version')
    extensions = {}
    readings = {}
    for row in legacy['analyses']:
        easy = row.pop('easy_read', None)
        if easy is not None:
            strings(easy, ('happened', 'importance', 'business', 'product', 'data', 'action', 'career', 'question'))
            if sum(len(v) for v in easy.values()) > 1800:
                raise ValueError('쉬운 기사 분석은 전체 1800자 이내로 작성하세요.')
            readings[insight.canonical_url(row['url'])] = easy
        p = row.pop('planning', None)
        if not isinstance(p, dict) or set(p) != {'summary', 'comparison', 'hypothesis', 'decisions', 'roles'}:
            raise ValueError('요약·비교·가설·의사결정·담당자 제안이 필요합니다.')
        insight.text(p['summary'])
        if len(p['summary']) > 90 or '\n' in p['summary'] or '<' in p['summary']:
            raise ValueError('첫 화면 요약은 줄바꿈 없는 90자 이내 한 문장입니다.')
        insight.array(p['comparison'])
        for c in p['comparison']:
            strings(c, ('target', 'known', 'unknown'))
        strings(p['hypothesis'], ('text', 'basis', 'verify', 'refute'))
        strings(p['roles'], ('product', 'business'))
        insight.array(p['decisions'])
        for d in p['decisions']:
            strings(d, ('kpi', 'basis', 'supports', 'otherwise'))
        names = [k['name'] for k in row['kpis']]
        linked = [d['kpi'] for d in p['decisions']]
        if len(names) != len(set(names)) or len(linked) != len(set(linked)) or set(names) != set(linked):
            raise ValueError('각 KPI에 비교 기준과 의사결정이 정확히 하나씩 필요합니다.')
        extensions[insight.canonical_url(row['url'])] = p
    result = insight.combine(collection, legacy)
    result['schema_version'] = 2
    for item in result['items']:
        item['career_insight']['planning'] = extensions[item['url']]
        if item['url'] in readings:
            item['career_insight']['easy_read'] = readings[item['url']]
    return result

def easy_body(easy):
    labels = [('happened', '🚗 무슨 일이 있었나?'), ('importance', '💡 왜 중요한가?'), ('business', '💼 사업기획 관점'), ('product', '🚘 상품기획 관점'), ('data', '📊 어떤 데이터를 볼까?'), ('career', '🎤 취업에 어떻게 활용할까?'), ('action', '🧪 내가 해볼 것')]
    lines = []
    for field, label in labels:
        lines += ['### ' + label, easy[field]]
        if field == 'product':
            lines += ['두 직무 관점은 기사에 기반한 AI의 실무 해석입니다. 별도 출처를 명시한 인용 외에는 실제 현업자 발언이나 기업 내부 판단이 아닙니다.']
    lines += ['### ✍️ 내 생각을 위한 질문', easy['question'], '아래 내 생각 칸에 의견을 2~3줄로 적어보세요.']
    return '\n'.join(lines) + '\n'

def fold_details(content):
    return '<details>\n<summary>🔬 더 깊게 분석하기</summary>\n' + '\n'.join('\t' + line for line in content.rstrip().splitlines()) + '\n</details>\n'

def analysis_body(i, level=2):
    h, p = '#' * level, i['planning']
    lines = [f'{h} 무엇이 달라졌는가', i['what_changed']['text'], f'{h} 비교 기준']
    for c in p['comparison']:
        lines += [f"**{c['target']}**", f"- 확인된 내용·비교 설계: {c['known']}", f"- 미확인·추가 확인: {c['unknown']}"]
    q = p['hypothesis']
    lines += [f'{h} 기획 가설', q['text'], f"- 근거: {q['basis']}", f"- 확인할 데이터: {q['verify']}", f"- 가설이 약해지는 조건: {q['refute']}"]
    for field, label in [('business_view', '사업기획 관점'), ('product_view', '상품기획 관점')]:
        lines += [f'{h} {label} · 기획 제안', i[field]['text']]
    lines += [f'{h} KPI → 의사결정', '아래는 확인할 데이터와 판단 제안입니다. 실제 성과나 확정된 판단 기준이 아닙니다.']
    decisions = {d['kpi']: d for d in p['decisions']}
    for k in i['kpis']:
        d = decisions[k['name']]
        lines += [f"{h}# {k['name']}", f"- 뜻·계산: {k['definition']}", f"- 알고 싶은 것: {k['why']}", f"- 확인할 곳: {k['data_source']} / {k['availability']}", f"- 비교 기준: {d['basis']}", f"- 결과에 따른 판단: {d['supports']}", f"- 반대 결과일 때: {d['otherwise']}"]
    return '\n'.join(lines) + '\n'

def exercise_body(i, level=2):
    h, p, a = '#' * level, i['planning'], i['action']
    lines = [f'{h} 내가 담당자라면', '아래는 AI가 제안하는 접근 예시입니다. 나의 의견과 실제 수행 결과는 직접 작성합니다.', f'{h}# 내가 상품기획자라면', p['roles']['product'], f'{h}# 내가 사업기획자라면', p['roles']['business'], f"{h} 작은 실습 · 검증 Action · 약 {a['minutes']}분", a['task'], f"만들 결과: {a['deliverable']}", '실습 후 ‘내 생각과 실습’ 보기의 실습 결과·실습 링크에 남기고 검증 상태를 직접 바꿔 주세요. 조사 설계와 실제 가설 검증은 구분해 기록합니다.', f'{h} 더 생각해볼 질문']
    return '\n'.join(lines + ['- ' + q for q in i['questions']]) + '\n'

def render(data):
    lines = ['# Auto Career Brief · 기획 가설과 검증', f"수집 기준일: {data['as_of']} · 생성: {data['generated_at']}", '']
    for item in data['items']:
        i = item['career_insight']
        article_start = len(lines)
        lines += [f"## {item['title']}", i['planning']['summary'], '### 원문 사실 요약']
        lines += [f'{n}. {s}' for n, s in enumerate(item['summary'], 1)]
        lines += [analysis_body(i, 3), '### 취업 활용']
        lines += [f"- {u['type']}: {u['how']}" for u in i['career_uses']]
        lines += [exercise_body(i, 3), '### 아직 알 수 없는 점']
        lines += ['- ' + x for x in i['limitations']]
        if 'easy_read' in i:
            lines[article_start:] = [f"## {item['title']}", i['planning']['summary'], easy_body(i['easy_read'])]
        lines += ['### 내 생각 · 직접 작성', '', '### 실습 결과 · 직접 작성', '', '### 출처', f"[{item['source']}]({item['url']})", f"발행일: {item['published_date']} · 자료 구분: {item['freshness']}", '']
    return '\n'.join(lines + ['## 원본 연결', data['source_collection'], data['source_collection_sha256'], '외부 저장 여부는 별도 전송 기록을 확인합니다.']) + '\n'

def save(collection_path, analyses_path, output):
    raw = Path(collection_path).read_bytes()
    data = combine(json.loads(raw.decode('utf-8-sig')), json.loads(Path(analyses_path).read_text(encoding='utf-8-sig')))
    data.update(source_collection=Path(collection_path).name, source_collection_sha256=hashlib.sha256(raw).hexdigest(), generated_at=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    version = 1
    while True:
        stem = f"auto-career-brief-planning-{data['as_of']}-{data['mode']}-v{version:02d}"
        jp, mp = output / (stem + '.json'), output / (stem + '.md')
        if not jp.exists() and not mp.exists():
            break
        version += 1
    with jp.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with mp.open('x', encoding='utf-8') as f:
        f.write(render(data))
    return jp, mp

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('collection', 'analyses', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        for path in save(args.collection, args.analyses, args.output):
            print(path.resolve())
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'기획 분석 저장 실패: {error}\n')
