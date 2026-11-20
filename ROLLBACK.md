# 되돌리기 절차 (v1.0.0 → v0.4.0)

M7(2026-11-20)에 실제로 시험해 확정한 절차입니다.

## 설치 구조
- v1.0.0은 로컬 마켓플레이스 `dsc-local`(`dwelling-sermon-coach_versions/.claude-plugin/marketplace.json`)로 설치되어 있습니다. 이름: `dwelling-sermon-coach@dsc-local`, 범위 user.
- 설치본은 **이 폴더(`v1.0.0`)를 바로 읽습니다.** 여기서 고친 것은 새 대화부터 바로 쓰입니다. (2026-11-20 새 세션에서 확인. 반영되지 않으면 `claude plugin marketplace update dsc-local` 뒤 새 대화)
- claude.ai 계정의 구판 `dwelling-sermon-coach@synced`(My Uploads v0.4.0)는 그대로 둡니다. 같은 이름이라 로컬 설치가 켜져 있는 동안은 읽히지 않습니다.

## 1. 되돌리기 (한 줄)
```bash
claude plugin disable dwelling-sermon-coach@dsc-local
```
- 새 대화를 열면 구판 v0.4.0이 다시 읽힙니다. 「머무르는 설교 코치 시작」에 **7단계** 시작 문구가 나오면 된 것입니다(시험 확인).
- 작업창 서버가 켜져 있으면 Ctrl+C로 끕니다.

## 2. 다시 v1.0.0으로
```bash
claude plugin enable dwelling-sermon-coach@dsc-local
```
- 새 대화에서 **9단계** 시작 문구가 나오면 된 것입니다(시험 확인).

## 3. 계정의 구판까지 없어졌을 때
- 압축본: `~/DSC/dwelling-sermon-coach_versions/dwelling-sermon-coach_v0.4.0.zip` (폴더 백업: `…/v0.4.0`)
- claude.ai에서 이 압축본을 다시 올리거나, `claude plugin marketplace add`로 `v0.4.0` 폴더를 담은 로컬 마켓플레이스를 만들어 설치합니다.
- v1.0.0 압축본: `…/dwelling-sermon-coach_v1.0.0.zip`

## 4. 설교 폴더
- v1.0.0이 만든 `00_수집/`, `03_원어관찰.json`, `progress.json`은 v0.4.0이 읽지 않습니다. 지우지 않아도 됩니다.
- 목사님이 쓴 md 파일은 v1.0.0이 덮어쓰지 않으므로 그대로 남습니다.
- 설정 파일 `~/.config/dsc/dsc.config.json`은 v0.4.0이 쓰지 않습니다. 그대로 두어도 됩니다.
