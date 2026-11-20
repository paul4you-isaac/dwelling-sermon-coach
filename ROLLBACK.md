# 되돌리기 절차 (v1.0.0 → v0.4.0)

2026-11-20 확정. 데스크톱 앱(Chat·Code)은 **claude.ai 계정의 플러그인**을 읽습니다. 그래서 되돌리기도 계정에서 합니다.

## 설치 구조
| 자리 | 이름 | 상태 |
|---|---|---|
| claude.ai 계정 · GitHub 마켓플레이스 `paul4you-isaac/dwelling-sermon-coach` | Dwelling sermon coach (dwelling-sermon-coach) · **v1.0.0** | 켜짐 |
| claude.ai 계정 · My Uploads | Dwelling sermon coach (로컬 업로드) · v0.4.0 | 꺼짐 (지우지 않음) |
| claude.ai 계정 · Skills | dwelling-sermon-coach (2) · 7단계 | 꺼짐 (지우지 않음) |
| 이 컴퓨터 터미널(Claude Code) · 로컬 마켓플레이스 `dsc-local` | dwelling-sermon-coach@dsc-local · 개발 폴더 `v1.0.0`을 바로 읽음 | 켜짐 (개발·시험용) |

## 1. 되돌리기 — claude.ai 「사용자 지정 → 플러그인 → 내 항목」
1. **Dwelling sermon coach (dwelling-sermon-coach)** 줄의 「…」 → **끄기**
2. **Dwelling sermon coach (로컬 업로드)** 줄의 「…」 → **켜기**
3. 데스크톱 앱을 완전히 끄고(⌘Q) 다시 켠 뒤 새 대화에서 「머무르는 설교 코치 시작」 → **7단계** 문구가 나오면 된 것입니다.

터미널에서도 구판을 쓰려면:
```bash
claude plugin disable dwelling-sermon-coach@dsc-local
```

## 2. 다시 v1.0.0으로
위 1·2를 반대로 하고(새 판 켜기, 로컬 업로드 끄기), 앱을 다시 켭니다. 새 대화에서 **9단계** 문구가 나오면 된 것입니다.
터미널: `claude plugin enable dwelling-sermon-coach@dsc-local`

## 3. 새 판을 고쳐 올릴 때
- 개발 폴더 `v1.0.0`에서 고치고 시험한 뒤 GitHub `main`에 올립니다.
- claude.ai 플러그인 화면에서 그 마켓플레이스를 「동기화」하면 계정에 반영됩니다. (자동 동기화는 Claude GitHub 앱에 저장소 권한을 줘야 켜집니다. 아직 주지 않았습니다.)

## 4. 계정의 구판까지 없어졌을 때
- 압축본 `~/DSC/dwelling-sermon-coach_versions/dwelling-sermon-coach_v0.4.0.zip` (폴더 백업: `…/v0.4.0`)을 claude.ai 「플러그인 업로드」로 다시 올립니다.
- GitHub 저장소의 v0.3.0 기록(커밋 `fe7188f`)도 남아 있습니다.
- v1.0.0 압축본: `…/dwelling-sermon-coach_v1.0.0.zip`

## 5. 설교 폴더
- v1.0.0이 만든 `00_수집/`, `03_원어관찰.json`, `progress.json`은 v0.4.0이 읽지 않습니다. 지우지 않아도 됩니다.
- 목사님이 쓴 md 파일은 v1.0.0이 덮어쓰지 않으므로 그대로 남습니다.
- 설정 파일 `~/.config/dsc/dsc.config.json`은 v0.4.0이 쓰지 않습니다.
