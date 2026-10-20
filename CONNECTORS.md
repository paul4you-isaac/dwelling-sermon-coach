# Connectors

## 개인 정보 설정

이 플러그인은 설교자 이름과 교회 이름을 산출물 파일에 자동으로 기록합니다.
플러그인 설치 후 아래 플레이스홀더를 본인 정보로 교체하십시오.

## 플레이스홀더 목록

| 플레이스홀더 | 의미 | 예시 |
|---|---|---|
| `~~preacher-name` | 설교자 이름 | `홍길동 목사` |
| `~~church-name` | 교회 이름 | `○○교회` |
| `~~church-slogan` | 교회 슬로건 (확장판) | `말씀으로 세워지는 교회` |
| `~~sermon-vault` | 설교 Obsidian 볼트 경로 (확장판) | `/Users/me/SERMONS` |
| `~~shared-folder` | HTML 공유용 iCloud 폴더 (확장판, 선택) | `~/Library/Mobile Documents/com~apple~CloudDocs/sermon-shared` |

## 교체 방법

### 방법 1 — cowork-plugin-customizer 사용 (권장)

Claude Cowork에서 다음과 같이 입력합니다:

```
dwelling-sermon-coach 플러그인의 preacher-name을 [목사님 이름]으로,
church-name을 [교회 이름]으로 설정해 주세요.
```

### 방법 2 — 파일 직접 수정

`skills/dwelling-sermon-coach/references/output-templates.md` 파일을 열어
`~~preacher-name`과 `~~church-name`을 직접 교체합니다.
확장판(`skills/dwelling-sermon-coach-2/`)은 `SKILL.md`와 `references/` 아래 모든 파일에서
위 표의 플레이스홀더를 일괄 교체합니다.

## 기본 번역 설정 (선택)

산출물 YAML의 기본 성경 번역을 변경하려면
스킬 파일 내 `본문 인용은 개역개정 기본` 부분을 원하는 번역으로 수정합니다.

지원 번역: 개역개정, 새번역, 새한글(2024), 공동번역 개정판, ESV
