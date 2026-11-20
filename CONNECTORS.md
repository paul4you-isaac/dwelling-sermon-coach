# Connectors · 설정

## 개인 설정 파일

개인 정보와 경로는 플러그인 안이 아니라 **`~/.config/dsc/dsc.config.json`**에 둡니다.
플러그인을 업데이트해도 설정이 지워지지 않습니다.
예시: `config/dsc.config.example.json`

| 키 | 의미 |
|---|---|
| `vault_root` | 주간 폴더(`S_{주일}`)가 생기는 Obsidian 볼트 경로 |
| `input_root` | 입력 자료 폴더 |
| `materials_dirs` | 설교자가 지정한 주석 자료 폴더 목록 |
| `md_commentary_glob` | 변환된 md 주석 파일 패턴 (기본 `B_*.md`) |
| `logos_bridge` | Logos 브리지 스크립트 경로 (`logos` 스킬) |
| `port` | 관찰 작업창 포트 (기본 8787) |
| `claude_bin` | 작업창 「감독에게 묻기」가 부를 `claude` 실행 파일. 비우면 PATH → `~/.local/bin/claude` 순서로 찾음 |
| `ask_model` | 「감독에게 묻기」 모델 (기본 `sonnet`) |
| `preacher` · `church` · `church_slogan` | 산출물 YAML과 교회 비전 환기에 쓰는 이름 |
| `stage3_private` | Stage 3 원어관찰의 묵상 노트를 7A처럼 비공개로 다룰지 (예전 이름 `stage3_apply_private`도 읽음) |

## 외부 연결

| 연결 | 용도 | 범위 |
|---|---|---|
| 대한성서공회 성경플랫폼 (`bible.bskorea.or.kr`) | 새한글·새번역·공동번역 개정판·개역개정 | 수집 스크립트 직접 요청 |
| die-bibel.de (독일성서공회, 같은 플랫폼) | NA28·BHS·ESV | 수집 스크립트 직접 요청 |
| 대한성서공회 구 읽기 화면 · biblegateway.com | 교차 검증 | 수집 스크립트 직접 요청 |
| Logos (로컬 앱) | 주석 수집 | 읽기 명령만 (`library`, `books`, `excerpt`) |
| 로컬 자료 폴더 | 주석 수집 | 읽기 |

주석은 웹에서 찾지 않습니다.

## 기본 번역

본문 인용은 개역개정이 기본입니다.
지원 번역: 개역개정, 새번역, 새한글(2024), 공동번역 개정판, ESV
