# 계약서 도우미 — 설계 메모

## 구조 (노무 서류 봇 nomudocs 와 같은 모양)
```
build/
  contractdocs/            # 파이썬 패키지 (python3 -m contractdocs ...)
    __main__.py            # check · make · review · score · laws
    checks.py              # 입력 점검: 빈칸·민감정보 차단·위험한 값 경고
    templates.py           # 외주용역 · 용역 · NDA 조항 (legal v3.4.0 템플릿 기반)
    generate.py            # JSON → DOCX + MD (+PDF/PNG) + 작성메모 + 점검결과.json
    docx_builder.py        # '맑은 고딕' 표기, 면책 고지 맨 위 1회 (nomu 와 같은 글꼴 규칙)
    render.py              # soffice → PDF, pdftoppm → PNG, render/fonts.conf 로 Noto Sans CJK KR 대체
    laws.py                # 근거 조문표 (2026-11-09 법제처 원문 대조, 미대조는 [확인 필요])
    review/
      extract.py           # txt·md·docx·pdf·hwpx(내장)·hwp(pyhwp 있으면)
      rules.py             # 규칙 기반 독소 12종·7대·5빠진·미수금 5장치 (결정론)
      catalog.py           # 이유·고칠 문장·말하는 방법 (원본 카탈로그 + 조문 정정)
      score.py             # 원본 score.py 와 같은 공식 (시험이 4096가지 조합 전수 대조)
      report.py            # MD → DOCX → PDF 리포트
  render/fonts.conf        # 박스 렌더링 전용 글꼴 별칭 (nomu 와 같은 내용)
  samples/input/*.json     # 견본 입력 3종 (가상 값)
  samples/review/*         # 시험용 독소 계약서 3건 (txt·docx·pdf, 가상)
  out/                     # 견본 결과물
  tests/test_all.py        # 자동 시험 (unittest)
  skills/*/SKILL.md        # 스킬 초안 2개
  bot_instructions.md      # 봇 지시문 초안
```

## 원본에서 바뀐 점
- MCP 없이 돈다: 조문 요지는 laws.py 에 내장, MCP 는 새 조문을 확인할 때만.
- 점검이 '봇이 확정한 목록'에만 의존하지 않는다: 규칙이 확정/후보를 먼저 정하고, 봇은 후보만 원문을 읽고 --confirm/--reject 로 조정한다(조정 내역은 리포트에 남음). 같은 파일·같은 조정이면 늘 같은 점수.
- PDF 는 WeasyPrint·크롬 대신 노무 봇과 같은 LibreOffice 경로(박스에 이미 있음). build_report.py 는 쓰지 않는다.
- 면책 고지: 원본은 "모든 답변 시작에" → 결과물 맨 위 1회로 바꿈. 문구는 "변호사 검토 전 참고용 초안".
- 범위: 생성·점검 두 가지만. 원본의 상담준비(4종 묶음)·내용증명·용어 모드는 넣지 않음(내용증명은 상대방에게 보내는 법적 서면이라 변호사법 위험이 커서 뺌).
- biz-legal-team(이전 판)에서 가져온 것: 없음. 이전 판의 차이는 근거 조문 오류(민사소송법 제8조, 민법 제152·655조 등)와 '/my-lawyer' 의존뿐이고, v3.4.0 이 그것을 이미 고쳤다.

## 공유 봇에게 스크립트·글꼴이 어떻게 가나
- 봇 공유 템플릿에는 기억·스킬 글·루틴·플러그인만 담긴다. 박스의 파일(스크립트, 글꼴)은 따라가지 않는다. 받은 사장님 봇의 박스에는 이 코드가 없다.
- 안 A (권장): 공개 GitHub 저장소에 build/ 를 올리고 태그(v1)와 파일별 sha256 MANIFEST 를 둔다. 「시작하기」 스킬이 첫 대화 때 그 태그를 받아 sha256 을 확인한 뒤 설치한다. 세금정리도우미(lbiz-tax-helper)와 같은 방식이라 관리가 한 가지로 통일된다. 글꼴은 박스 기본 Noto Sans CJK KR 을 쓰고, 없으면 저장소에 나눔고딕(SIL OFL, 원본 assets/fonts 에 있음)을 같이 넣는다.
- 안 B: 코드 전체를 스킬 본문 안에 넣고 봇이 파일로 풀어 쓰게 한다. 저장소가 필요 없지만 스킬 크기 제한에 걸릴 수 있고(현재 코드 약 60KB), 고칠 때마다 스킬을 다시 배포해야 한다.
- 안 C: 도구 없이 스킬 글만으로 동작(업무 규칙 7장). 파일·점수 재현성은 포기한다. A·B 가 실패했을 때의 비상용.
