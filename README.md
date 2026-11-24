# 금융권 사업공고 보드

나라장터(조달청)에 게시된 금융 공공기관 12곳의 일반용역 사업공고를 최신 공고·기관별·검색으로 정리한 정적 페이지입니다.

- 페이지: `docs/` (바닐라 HTML/CSS/JS, 빌드 도구 없음). 데이터는 `docs/data/bids.json` 하나이며, 운영 수집기(`fin_bid_watch`)의 `fbw export`가 만듭니다.
- 출처: **나라장터(국가종합전자조달) 공개 입찰공고 정보**. 자동 수집·분류 결과이므로 정확한 내용은 각 공고의 '나라장터에서 보기' 원문을 확인해 주세요.
- 공개 필드만 싣습니다(사업명·기관·발주부서·금액·낙찰방법·게시/마감일시·공고번호·주제). 담당자명·원문 데이터·첨부파일은 싣지 않습니다.
- 검색엔진 수집 차단: `<meta name="robots" content="noindex">` + `docs/robots.txt`(`Disallow: /`).
- 주제는 사업명 키워드 규칙으로 분류한 참고값입니다(미일치 = 기타).
- D-day는 보는 사람의 브라우저가 한국 시간(KST) 기준으로 계산합니다.

## 바로가기(해시 라우팅)
- `#/latest` 최신 공고(게시일 묶음, 첫 화면)
- `#/org` · `#/org/<기관 ID>` 기관별 (예: `#/org/kdb`)
- `#/search?q=<검색어>` 검색(공고명·기관·발주부서·공고번호)
- `#/bid/<공고번호-차수>` 공고 상세 (예: `#/bid/R26BK01801206-000`)

## 검증
`/usr/bin/python3 tests/verify_board.py --db <fbw.db 읽기 전용 사본> --out <폴더>` — Playwright(Chromium)로 390·1280px × 라이트/다크 캡처, 콘솔 오류, 렌더 건수, 검색 건수(DB 대조), 라우트 직접 진입을 점검합니다.

## 라이선스
- 글꼴: [Pretendard](https://github.com/orioncactus/pretendard) (SIL Open Font License 1.1, jsDelivr CDN)
- 아이콘: [Material Symbols Rounded](https://fonts.google.com/icons) (Apache License 2.0, Google Fonts)
- 디자인 토큰: 토스 TDS 3.0 색상값(금융권 인사 보드 `fin-promo-board`와 동일)
