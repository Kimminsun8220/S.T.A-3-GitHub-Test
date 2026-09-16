"""Bot-only Slack delivery with durable, per-part deduplication. Stdlib only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.request


class DeliveryError(Exception):
    pass


def validate(payload):
    for key, pattern in [('workspace', r'T[A-Z0-9]+'), ('channel', r'[CG][A-Z0-9]+')]:
        if not re.fullmatch(pattern, str(payload.get(key, ''))):
            raise DeliveryError('workspace/channel ID가 필요합니다.')
    if not isinstance(payload.get('issue_id'), str) or not payload['issue_id'].strip():
        raise DeliveryError('같은 발행 회차에서 유지할 issue_id가 필요합니다.')
    messages = payload.get('messages')
    if not isinstance(messages, list) or not 2 <= len(messages) <= 4:
        raise DeliveryError('메인 1개와 기사 댓글 1~3개가 필요합니다.')
    if any(not isinstance(m, str) or not m.strip() or len(m) > 4000 for m in messages):
        raise DeliveryError('각 메시지는 1~4000자여야 합니다.')
    return messages


def digest(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS issues (
            workspace TEXT, channel TEXT, issue TEXT, hash TEXT, bot TEXT,
            PRIMARY KEY(workspace,channel,issue));
        CREATE TABLE IF NOT EXISTS parts (
            workspace TEXT, channel TEXT, issue TEXT, part INTEGER,
            state TEXT, ts TEXT,
            PRIMARY KEY(workspace,channel,issue,part));
    ''')
    return db


class Slack:
    def __init__(self, token):
        if not token.startswith('xoxb-'):
            raise DeliveryError('SLACK_BOT_TOKEN에 봇 토큰이 필요합니다.')
        self.token = token

    def __call__(self, method, body):
        request = urllib.request.Request(
            'https://slack.com/api/' + method,
            data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + self.token,
                     'Content-Type': 'application/json; charset=utf-8'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            # Do not print raw network exceptions or credentials; no blind retry.
            raise DeliveryError('응답을 확인할 수 없습니다. 전송 기록과 Slack을 대조하세요.') from None


def deliver(payload, ledger, api, pause=time.sleep):
    messages = validate(payload)
    identity = api('auth.test', {})
    if not identity.get('ok') or not identity.get('bot_id'):
        raise DeliveryError('봇 인증에 실패했습니다.')
    if identity.get('team_id') != payload['workspace']:
        raise DeliveryError('대상 워크스페이스와 봇 계정이 다릅니다.')
    key = (payload['workspace'], payload['channel'], payload['issue_id'])
    db = connect(ledger)
    try:
        # BEGIN IMMEDIATE serializes competing workers before claiming each part.
        with db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT hash,bot FROM issues WHERE workspace=? AND channel=? AND issue=?', key).fetchone()
            expected = (digest(messages), identity['bot_id'])
            if prior and prior != expected:
                raise DeliveryError('같은 회차의 내용 또는 봇이 바뀌었습니다. 새 전송 대신 기존 메시지 편집을 검토하세요.')
            db.execute('INSERT OR IGNORE INTO issues VALUES (?,?,?,?,?)', (*key, *expected))
        results = []
        parent = None
        for index, message in enumerate(messages):
            with db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT state,ts FROM parts WHERE workspace=? AND channel=? AND issue=? AND part=?', (*key, index)).fetchone()
                if previous and previous[0] == 'sent':
                    results.append({'part': index, 'status': 'skipped', 'ts': previous[1]})
                    if index == 0:
                        parent = previous[1]
                    continue
                if previous and previous[0] == 'pending':
                    raise DeliveryError(f'{index}번 전송 결과가 불확실하거나 다른 실행이 처리 중입니다. 자동 재전송을 중단합니다.')
                db.execute('INSERT OR REPLACE INTO parts VALUES (?,?,?,?,?,?)', (*key, index, 'pending', None))
            body = {'channel': payload['channel'], 'text': message,
                    'unfurl_links': False, 'unfurl_media': False}
            if index:
                body['thread_ts'] = parent
                pause(1.1)
            response = api('chat.postMessage', body)
            if not response.get('ok'):
                error = response.get('error', '')
                # These definitive rejections did not create a message. Others stay pending.
                if error in {'not_in_channel', 'channel_not_found', 'missing_scope', 'invalid_auth',
                             'token_revoked', 'account_inactive', 'is_archived', 'msg_too_long', 'no_text', 'ratelimited'}:
                    with db:
                        db.execute('UPDATE parts SET state=? WHERE workspace=? AND channel=? AND issue=? AND part=?', ('failed', *key, index))
                raise DeliveryError(f'{index}번 전송 실패. 성공한 부분은 보존했습니다. 권한과 Slack 상태를 확인하세요.')
            ts = response.get('ts')
            if (response.get('channel') != payload['channel'] or
                    response.get('message', {}).get('bot_id') != identity['bot_id'] or
                    not isinstance(ts, str) or not re.fullmatch(r'\d+\.\d+', ts)):
                raise DeliveryError('전송 응답의 채널·봇·메시지 ID가 불일치합니다. 재전송하지 않습니다.')
            with db:
                db.execute('UPDATE parts SET state=?,ts=? WHERE workspace=? AND channel=? AND issue=? AND part=?', ('sent', ts, *key, index))
            results.append({'part': index, 'status': 'sent', 'ts': ts})
            if index == 0:
                parent = ts
        return results
    finally:
        db.close()


def adopt_receipts(payload, ledger, receipts):
    """Import a complete prior delivery only after its thread was verified externally."""
    messages = validate(payload)
    rows = sorted(receipts, key=lambda row: row['index'])
    if (len(rows) != len(messages) or [r['index'] for r in rows] != list(range(len(messages)))
            or any(r.get('ok') is not True or r.get('channel') != payload['channel']
                   or not r.get('bot_id') or not re.fullmatch(r'\d+\.\d+', str(r.get('ts', ''))) for r in rows)
            or len({r['bot_id'] for r in rows}) != 1 or len({r['ts'] for r in rows}) != len(rows)):
        raise DeliveryError('기존 전송 기록이 완전하지 않습니다.')
    db = connect(ledger)
    key = (payload['workspace'], payload['channel'], payload['issue_id'])
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM issues WHERE workspace=? AND channel=? AND issue=?', key).fetchone():
                raise DeliveryError('해당 회차는 이미 기록되어 있습니다. 덮어쓰지 않습니다.')
            db.execute('INSERT INTO issues VALUES (?,?,?,?,?)', (*key, digest(messages), rows[0]['bot_id']))
            db.executemany('INSERT INTO parts VALUES (?,?,?,?,?,?)', [(*key, r['index'], 'sent', r['ts']) for r in rows])
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--ledger', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--send', action='store_true')
    mode.add_argument('--adopt-receipts', type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding='utf-8-sig'))
    validate(payload)
    if args.adopt_receipts:
        receipts = [json.loads(line) for line in args.adopt_receipts.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        adopt_receipts(payload, args.ledger, receipts)
        print('기존 발송 기록을 등록했습니다. 외부 전송 없음.')
    elif args.send:
        print(json.dumps(deliver(payload, args.ledger, Slack(os.environ.get('SLACK_BOT_TOKEN', ''))), ensure_ascii=False))
    else:
        print(json.dumps({'mode': 'preview', 'channel': payload['channel'], 'messages': payload['messages']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (DeliveryError, OSError, ValueError, sqlite3.Error) as exc:
        print(str(exc) if isinstance(exc, DeliveryError) else '입력 파일 또는 전송 기록을 확인하세요.')
        raise SystemExit(1)
