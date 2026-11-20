# Dwelling Sermon Coach v1.0

한 주 동안 성경 본문과 동행하며 묵상 중심으로 설교를 준비하는 **9단계 워크플로우** 플러그인입니다.
최주훈 목사의 「뭉근하게 본문에 머무르는」 설교 준비 방법론을 구현했습니다.

## 철학

이 플러그인의 가장 큰 가치는 **클로드가 빨리 답하지 않는 데** 있습니다.

- 분석을 먼저 제공하지 않습니다.
- 설교자가 본문을 직접 만나기 전에 의미·신학·맥락을 풀어 주지 않습니다.
- 설교자의 통찰을 받아 적습니다. 다시 쓰지 않습니다.
- 한 단계가 끝날 때까지 다음 단계로 가지 않습니다.
- 주석은 Stage 4 1차청중부터 보입니다.

## 구성

| 구성요소 | 내용 |
|---|---|
| 스킬 | `dwelling-sermon-coach` — 감독. 설교자가 대화하는 유일한 창구 |
| 에이전트 | `dsc-collector` 수집 · `dsc-archivist` 기록보관 |
| 관찰 작업창 | 로컬 웹앱(`127.0.0.1`). 헬라어 구문성경 「구문 묵상 뷰어」 틀 — 5중 인터리니어·주동사 해설·절별 묵상 노트 |
| 참조 문서 | 단계 대응표, 단계 가이드, 산출물 템플릿, YAML 규격, 디자인 시스템, 신학 프레임워크, 검증 정책, 운영 패턴, 에이전트 규약 |

## 설치

GitHub 저장소 `paul4you-isaac/dwelling-sermon-coach`가 그대로 마켓플레이스입니다.

- **claude.ai·데스크톱 앱**: 사용자 지정 → 플러그인 → 마켓플레이스 추가에서 `paul4you-isaac/dwelling-sermon-coach`를 넣고 `dwelling-sermon-coach`를 설치합니다.
- **터미널(Claude Code)**:
```bash
claude plugin marketplace add paul4you-isaac/dwelling-sermon-coach
claude plugin install dwelling-sermon-coach@dwelling-sermon-coach --scope user
```
- 예전에 올린 구판(My Uploads v0.4.0)과 이름이 같습니다. 새 판을 쓰는 동안 구판은 꺼 둡니다.
- 되돌리기는 `ROLLBACK.md`, 사용 안내는 `docs/manual.html`입니다.
- 성경 번역 본문이 든 시안·견본 HTML은 저작권 때문에 저장소에 넣지 않았습니다.

## 설치 후 설정

`config/dsc.config.example.json`을 `~/.config/dsc/dsc.config.json`으로 복사해 값을 채웁니다.
설교자 이름, 교회 이름, 볼트 경로, 자료 폴더, Logos 브리지 경로, 작업창 포트를 여기에 둡니다.
자세한 항목은 `CONNECTORS.md`를 참조합니다.

### 권한 (하위 에이전트용)
수집·기록보관 에이전트는 이 플러그인의 스크립트 세 개만 Bash로 실행합니다.
매번 묻지 않게 하려면 `~/.claude/settings.json`의 `permissions.allow`에 아래 세 줄을 넣습니다.

```json
"Bash(python3 *dsc_collect.py*)",
"Bash(python3 *dsc_archive.py*)",
"Bash(python3 *check_privacy.py*)"
```
권한이 없으면 에이전트는 우회하지 않고 「거절」과 이유만 돌려줍니다.

### 관찰 작업창 켜기
터미널에서 플러그인 폴더로 가서 아래 명령을 실행합니다. Python 표준 라이브러리만 씁니다.

```bash
python3 app/server.py
```
- 주소는 `http://127.0.0.1:8787`입니다(설정 `port`). 이 컴퓨터에서만 열립니다.
- 끄려면 그 터미널에서 Ctrl+C를 누릅니다. 기록은 입력할 때마다 주간 폴더에 저장되어 있습니다.
- Claude Code 데스크톱에서는 `.claude/launch.json`의 `dsc-workspace`로도 켤 수 있습니다.
- 켤 때마다 새 접속 토큰을 만듭니다. 서버를 다시 켰으면 열려 있던 작업창을 새로 고칩니다.

## 시작 방법

- `머무르는 설교 코치 시작`
- `다음 주일 설교 본문: [성경 본문]`
- `이번 주 설교 [성경 본문]으로 천천히 준비하고 싶어요`

설교 본문을 바로 입력하면 Stage 0 수집과 Stage 1 본문만남이 시작됩니다.

## 9단계 워크플로우

| 단계 | 내용 | 권장 요일 |
|---|---|---|
| Stage 0 | 수집 (번역본·원어) | 주일 오후 |
| Stage 1 | 본문만남 | 주일 오후 |
| Stage 2 | 동행일지 | 월·화 |
| Stage 3 | 원어관찰 (관찰 작업창) | 화·수 |
| Stage 4 | 1차청중 (주석 수집 시작) | 수 |
| Stage 5 | 맥락관찰 | 수·목 |
| Stage 6 | 묵직한단어 | 목 |
| Stage 7 | 오늘적용 (7A 자기 → 7B 회중) | 금 |
| Stage 8 | 원고점검 + 묵상종합 | 토 |
| Stage 9 | 설교개요 | 토 |

## 신학적 기반

- **Sola Gratia** · **FCF**(Bryan Chapell) · **Redemptive Trajectory**
- 도덕주의·율법주의 배제
- 상세: `skills/dwelling-sermon-coach/references/theological-framework.md`

## 산출물

Obsidian YAML 호환 마크다운과 단계별 HTML로 저장됩니다.
AI가 쓴 문장은 모두 【AI】로 표시됩니다.

## 연계 스킬 (별도 설치)

| 스킬 | 사용 시점 |
|---|---|
| `nt-clausal-outline` / `ot-clausal-outline` | Stage 3 원어관찰 구문 배열 보완 |
| `chapell-christ-centered` | Stage 7B 회중적용 그리스도 중심 다리 |
| `biblical-word-study` | Stage 6 묵직한단어 심화 |
| `pastoral-assistant` | Stage 5 맥락관찰 · Stage 6 묵직한단어 원어 보조 |
| `bible-exegesis-8steps` | Stage 5 맥락관찰 페리코프 보완 |
| `logos` | Stage 4 1차청중 이후 주석 (수집 에이전트 경유) |
| `sermon-editor` | Stage 9 설교개요 이후 원고 편집 |

## 되돌리기

문제가 생기면 `ROLLBACK.md` 절차로 v0.4.0으로 돌아갑니다.

## 버전

- v1.0.0 — 기본판·확장판 통합, 9단계(원어관찰·수집 신설), 감독·수집·기록보관 에이전트, 주석 게이트, 관찰 작업창, 공통 디자인 시스템, 【AI】 표시 통일
- v0.4.0 — TTS 울림 방지 4규칙 (확장판 v2.2.0)
- v0.3.0 — 확장판 v2.1.2 추가
- v0.2.0 — Stage 1 본문만남 비교성경 HTML 표준
- v0.1.0 — 초기 배포
