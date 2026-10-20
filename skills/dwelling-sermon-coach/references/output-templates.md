# 산출물 관리 규칙

## 파일명 규칙

```
{단계번호}_{단계명}_{날짜}_{본문}.md
```

예시:
- `01_본문만남_2026-05-11_창세기12_1-9.md`
- `02_동행일지_2026-05-12_로마서8_28-39.md`
- `06A_자기적용_2026-05-15_요한복음15_1-8.md`

날짜 형식: `YYYY-MM-DD`
본문 형식: `성경책명장_시작절-끝절` (공백 없이 언더스코어 사용)

## YAML frontmatter 필수 필드

```yaml
---
date: YYYY-MM-DD
text: 성경책 장:절
stage: 1-7
session: (단계 이름)
preacher: ~~preacher-name
church: ~~church-name
status: dwelling | ready
tags:
  - dwelling-sermon-coach
  - (본문책 영문 슬러그)
  - (단계별 태그)
---
```

`preacher`와 `church` 필드는 플러그인 설치 후 사용자가 직접 설정합니다.
설정 방법은 `CONNECTORS.md`를 참조합니다.

## Stage별 태그 목록

| Stage | 태그 |
|---|---|
| 1 (본문 만남) | `stage-1-encounter` |
| 2 (본문 동행) | `stage-2-dwelling` |
| 3 (청중 만나기) | `stage-3-audience` |
| 4 (맥락 살피기) | `stage-4-context` |
| 5 (묵직한 단어) | `stage-5-keyword` |
| 6A (자기 적용) | `stage-6a-self`, `private` |
| 6B (회중 적용) | `stage-6b-congregation` |
| 7 (원고 점검) | `stage-7-review` |

## Stage 6A 특별 처리

자기 적용 산출물에는 반드시 `private: true`를 추가합니다.

```yaml
---
date: YYYY-MM-DD
text: 성경책 장:절
stage: 6
session: 자기적용
preacher: ~~preacher-name
church: ~~church-name
private: true
status: dwelling
tags:
  - dwelling-sermon-coach
  - stage-6a-self
  - private
---
```

이 산출물은 외부 공유를 전제하지 않습니다.

## 완성 산출물 예시 (Stage 1)

```markdown
---
date: 2026-05-11
text: 창세기 12:1-9
stage: 1
session: 본문만남
preacher: ~~preacher-name
church: ~~church-name
status: dwelling
tags:
  - dwelling-sermon-coach
  - genesis
  - stage-1-encounter
---

# 본문 만남 — 창세기 12:1-9

## 첫 반응

(설교자가 말한 내용 그대로)

## 비교성경

비교성경은 `ask-exegesis-1-reading-v02` 형식을 따르는 HTML 아티팩트로 제공합니다.
앞 페리코페(새한글) → 본문 절별 비교(원어·직역·새한글·새번역·공동번역·개역개정) → 뒤 페리코페(새한글).
본문 텍스트는 설교자 제공분만 사용하며, 직역만 Claude가 작성합니다.

## 다음 단계

Stage 2 — 본문과 동행 (월요일부터 시작)
```

## Obsidian 연동 권장 설정

이 스킬의 산출물은 Obsidian YAML 형식과 호환됩니다.
Obsidian 볼트에 `설교준비/` 폴더를 만들고
각 주일 본문별 서브폴더를 생성하여 관리를 권장합니다.

```
설교준비/
├── 2026-05-17_창세기12_1-9/
│   ├── 01_본문만남_2026-05-11_창세기12_1-9.md
│   ├── 02_동행일지_2026-05-13_창세기12_1-9.md
│   └── ...
└── 2026-05-24_로마서8_28-39/
    └── ...
```
