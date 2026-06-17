# Dwelling Sermon Coach

한 주 동안 성경 본문과 동행하며 묵상 중심으로 설교를 준비하는 7단계 워크플로우 플러그인.

최주훈 목사의 「뭉근하게 본문에 머무르는」 설교 준비 방법론을 구현하였습니다.

## 철학

이 플러그인의 가장 큰 가치는 **클로드가 빨리 답하지 않는 데** 있습니다.

- 분석을 먼저 제공하지 않습니다.
- 설교자가 본문을 직접 만나기 전에 의미·신학·맥락을 풀어 주지 않습니다.
- 설교자의 통찰을 받아 적습니다. 다시 쓰지 않습니다.
- 한 단계가 끝날 때까지 다음 단계로 가지 않습니다.

## 구성

| 구성요소 | 내용 |
|---|---|
| 스킬 1개 | `dwelling-sermon-coach` — 7단계 설교 준비 코치 |
| 참조 문서 3종 | 단계별 가이드, 산출물 템플릿, 신학 프레임워크 |

## 설치 후 설정

플러그인 설치 후 개인 정보를 설정합니다. (`CONNECTORS.md` 참조)

```
설교자 이름: ~~preacher-name → 본인 이름으로 교체
교회 이름:   ~~church-name  → 교회 이름으로 교체
```

## 시작 방법

Claude Cowork에서 다음 중 하나를 입력합니다:

- `머무르는 설교 코치 시작`
- `다음 주일 설교 본문: [성경 본문]`
- `이번 주 설교 [성경 본문]으로 천천히 준비하고 싶어요`

또는 설교 본문을 바로 입력하면 Stage 1이 자동으로 시작됩니다.

## 7단계 워크플로우

| 단계 | 내용 | 권장 요일 |
|---|---|---|
| Stage 1 | 본문 만남 | 주일 오후 |
| Stage 2 | 본문과 동행 (일지) | 월·화·수 |
| Stage 3 | 1차 청중 만나기 | 수요일 |
| Stage 4 | 맥락 살피기 | 수·목 |
| Stage 5 | 묵직한 한 단어 | 목요일 |
| Stage 6 | 오늘 적용 (자기→회중) | 금요일 |
| Stage 7 | 원고 4문 점검 | 토요일 |

## 신학적 기반

- **Sola Gratia**: 은혜 중심 설교
- **FCF (Fallen Condition Focus)**: Bryan Chapell의 그리스도 중심 강해
- **Redemptive Trajectory**: 구속사적 본문 읽기
- 도덕주의·율법주의 배제

복음주의 개혁주의 전통을 기반으로 하며, 교단에 따라 조정 가능합니다.
(`references/theological-framework.md` 참조)

## 산출물

Obsidian YAML 호환 마크다운 파일로 저장됩니다.
각 Stage마다 별도 파일이 생성되어 한 주 설교 준비 과정이 기록으로 남습니다.

## 연계 스킬 (별도 설치 필요)

Stage 진행 중 다음 스킬과 연계할 수 있습니다:

| 스킬 | 사용 시점 |
|---|---|
| `chapell-christ-centered` | Stage 6 그리스도 중심 다리 심화 |
| `biblical-word-study` | Stage 5 핵심 단어 원어 연구 |
| `pastoral-assistant` | Stage 4-5 원어 분석 보조 |
| `bible-exegesis-8steps` | Stage 4 페리코프 분석 보완 |
| `sermon-editor` | Stage 7 이후 원고 편집 |
| `nt-clausal-outline` / `ot-clausal-outline` | Stage 4 본문 시각화 |

## 버전

- v0.1.0 — 초기 배포 버전
