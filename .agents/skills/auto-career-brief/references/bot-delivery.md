# 봇 발송과 중복 방지

사용자가 승인한 채널에 봇 명의로 발송한다. 개인 계정 전송 도구로 대체하지 않는다. `scripts/slack_delivery.py`는 Python 표준 라이브러리만 사용한다. 예약 실행 기능은 없다.

## 입력

프로젝트 output에 새 파일로 저장한다. Slack 형식 `*강조*`, `<https://주소|이름>`을 사용한다.

```json
{
  "workspace": "T_WORKSPACE_ID",
  "channel": "C_CHANNEL_ID",
  "issue_id": "auto-career-brief:2026-09-15",
  "messages": ["메인 안내와 요약집·전체 기사 표 링크", "기사 1 요약", "기사 2 요약", "기사 3 요약"]
}
```

workspace/channel은 실제 조회한 ID로 교체한다. 발행 회차 ID는 날짜별로 고정하며 파일 버전·문구 수정으로 바꾸지 않는다. 메시지는 메인 1개와 기사 댓글 최대3개, 각4000자 이하다. 보충 자료는 기간을 알리고, 실습은 Notion에만 둔다.

## 실행

항상 같은 프로젝트의 `output/slack-delivery.sqlite3`를 기록 파일로 사용한다. 아래 명령은 스킬 폴더 기준이다. 경로는 실제 프로젝트 위치에 맞춘다.

```text
python scripts/slack_delivery.py PAYLOAD.json --ledger PROJECT/output/slack-delivery.sqlite3
python scripts/slack_delivery.py PAYLOAD.json --ledger PROJECT/output/slack-delivery.sqlite3 --send
```

첫 명령은 미리보기만 수행한다. 실제 전송은 사용자가 승인한 경우에만 `--send`를 사용한다. 실행 프로세스의 `SLACK_BOT_TOKEN`에 기존 비밀 설정의 봇 토큰을 넣는다. 명령문·입력 JSON·Git·출력에 토큰 값을 적지 않는다. `auth.test`로 봇과 대상 workspace를 확인하고 `chat.postMessage` 응답의 봇·채널·메시지 ID를 검증한다. 봇에 chat:write 권한과 대상 채널 접근이 필요하다.

## 기록과 재실행

- 워크스페이스+채널+회차 기준으로 성공한 메시지는 건너뛴다. 일부 댓글만 명확하게 실패하면 다음 실행에서 그 부분부터 보낸다.
- 요청 전에 pending을 저장한다. 시간 초과·비정상 응답·실행 중단으로 결과를 모르면 pending으로 남겨 자동 재전송을 차단한다. Slack 스레드와 기록을 대조해 사람이 확인한 뒤 복구한다. 이 스크립트에는 강제 재전송 옵션이 없다.
- 같은 회차에서 내용 또는 봇이 바뀌면 차단한다. 수정 요청은 저장된 메시지 ID로 기존 메시지를 편집하는 별도 작업으로 처리한다. 새 회차 ID를 만들어 차단을 회피하지 않는다.
- SQLite 쓰기 잠금으로 같은 기록 파일을 사용하는 동시 실행을 제어한다. 기록을 삭제하거나 다른 파일·다른 컴퓨터에서 실행하면 중복 방지가 보장되지 않는다. 하나의 실행 위치와 기록 파일을 유지한다.
- 기존 발송을 도입할 때는 Slack에서 본문·댓글·봇·채널을 대조한 완전한 전송 영수증(JSONL)을 `--adopt-receipts RECEIPTS.jsonl`로 등록한다. 각 줄은 index(0부터), ok=true, channel, bot_id, ts를 포함한다. 이 명령은 외부 검증을 대신하지 않으며, 이미 등록된 회차는 덮어쓰지 않는다.
- 성공 후 연결 도구로 스레드를 다시 읽어 본문·댓글과 발신자가 봇인지 확인한다. 1회 전송과 예약 설정을 구분해 보고한다.

공식 API: [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/), [auth.test](https://docs.slack.dev/reference/methods/auth.test/).
