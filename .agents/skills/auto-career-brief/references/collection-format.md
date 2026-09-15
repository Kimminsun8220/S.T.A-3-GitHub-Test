# 수집 결과 형식

최상위 필드:
- `as_of`: 한국 기준일, YYYY-MM-DD
- `days`: 기본 기간 일수, 양의 정수
- `mode`: industry / job / both
- `queries`: 실제 실행한 검색어 문자열 목록
- `items`: 아래 자료 목록
- `held`: 본문 미확인 등 보류 목록. 각 항목은 title, url, reason.

각 자료:
- `title`, `source`: 원문 제목과 발행 기관
- `url`: 실제로 열어 본 http(s) 원문 주소
- `published_date`: 원문에서 확인한 YYYY-MM-DD 또는 null
- `date_evidence`: 날짜 확인 근거 또는 날짜 미확인 사유
- `category`: 시장 / 고객·상품 / 사업·BM / 직무·채용 중 하나
- `search_mode`: industry / job 중 자료를 발견한 경로
- `company`: 기업명 문자열 목록
- `summary`: 원문에서 확인한 사실 3개를 담은 문자열 목록
- `relevance`: AI가 제안하는 취업 준비 자료로 선정한 이유
- `my_thought`: 빈 문자열. 사용자의 직접 작성 영역
- `source_verified`: 본문 확인 후에만 true

스크립트가 추가하는 값:
- `freshness`: recent(기본 기간) / expanded(최근 30일 내 보충) / background(오래된 직무 자료) / undated(날짜 미확인)
- `collected_date`: as_of와 동일한 수집 기준일

뉴스의 발행일과 사건 발생일은 구분한다. 본문 미확인 자료는 items에 넣지 않고 held로 보낸다. 최신 공고를 찾지 못해도 오래된 인터뷰를 최신 공고처럼 소개하지 않는다.
