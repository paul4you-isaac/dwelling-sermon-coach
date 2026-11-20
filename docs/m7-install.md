# M7 기록 — 설치·전환 (2026-11-20)

## 한 일
- 실제 설정 파일 `~/.config/dsc/dsc.config.json`(권한 600)을 만들었습니다. `vault_root`는 실사용 `…/주간묵상 설교준비/output`, Logos 브리지는 실제 경로입니다. 주석 자료 폴더(`materials_dirs`)는 비워 두었습니다.
- 로컬 마켓플레이스 `dsc-local`(`dwelling-sermon-coach_versions/.claude-plugin/marketplace.json`)을 만들고 `dwelling-sermon-coach@dsc-local`(user)로 설치했습니다. `claude plugin validate` 통과.
- 설치본은 `v1.0.0` 폴더를 바로 읽습니다(캐시 복사본이 아님).
- 매뉴얼 `docs/manual.html`을 디자인 시스템(작업대)으로 새로 만들었습니다. `check_html.py --mobile` 오류 0.
- 압축본 `dwelling-sermon-coach_v1.0.0.zip`(123개 파일, `.git`·캐시 제외)을 보관했습니다. 개인 정보·7A 파일 없음.
- `tools/check_html.py`: 상대 경로를 넘기면 멈추던 문제를 고쳤습니다.

## 완료 기준
| 기준 | 결과 |
|---|---|
| 새 대화에서 v1.0.0이 시작됨 | ✓ 사용자 설정 그대로 연 새 세션에서 「머무르는 설교 코치 시작」 → `dwelling-sermon-coach:dwelling-sermon-coach`, **9단계** 시작 문구 |
| 하위 에이전트 2종이 보임 | ✓ `dwelling-sermon-coach:dsc-collector` · `dsc-archivist` |
| 중복 트리거 0개 | ✓ 설교자가 claude.ai 「사용자 지정 → Skills → 내 항목」에서 `dwelling-sermon-coach (2)`를 끔(「…」 메뉴의 「끄기」). 새 세션에서 트리거를 가진 스킬은 `dwelling-sermon-coach:dwelling-sermon-coach` 하나 |
| `ROLLBACK.md` 절차를 한 번 시험 | ✓ `disable` → 새 세션에서 구판 **7단계** 시작 문구 → `enable` → 다시 v1.0 우선 |

## 작업창
- 실제 설정으로 켜서 실제 볼트의 두 주간(S_20261108·S_20261115)을 구판(읽기 전용)으로 읽었습니다. `/healthz` 정상. 확인 뒤 껐습니다.

## M0 결정에서 바뀐 것
- M0에서는 claude.ai의 구판 업로드(My Uploads v0.4.0)를 끄기로 했습니다. 실제로는 같은 이름의 로컬 설치가 우선해 **끌 필요가 없습니다.** 켜 둔 채 두면 되돌리기가 한 줄(`disable`)이 됩니다.
- 끌 것은 계정 스킬 `dwelling-sermon-coach-2` 하나입니다.

## 독립 점검 (verifier, sonnet)
- 명령·이름·범위·가림(shadowing)·설정 경로·작업창 명령·HTML 점검·시험 46개 모두 통과.
- 의문 1건: `~/.claude/plugins/cache/dsc-local/…/1.0.0`에 설치 때의 사본이 있어 「폴더를 바로 읽는다」가 확실한지 물었습니다.
  → 새 세션에서 스킬을 불러 확인하니 Base directory가 `…/dwelling-sermon-coach_versions/v1.0.0/skills/dwelling-sermon-coach`였습니다. 폴더를 바로 읽습니다.
  고친 것이 반영되지 않으면 `claude plugin marketplace update dsc-local` 뒤 새 대화를 엽니다(ROLLBACK.md에도 적음).
