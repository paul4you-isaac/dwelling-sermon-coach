# 에이전트 위임 규약 (v1.0)

감독(이 스킬)이 하위 에이전트에게 일을 맡길 때의 형식입니다.
설교자는 하위 에이전트와 직접 대화하지 않습니다.

## 1. 호출

| 에이전트 | 호출 이름 | 모델 | 도구 |
|---|---|---|---|
| 수집 | `dwelling-sermon-coach:dsc-collector` | sonnet | Bash, Glob |
| 기록보관 | `dwelling-sermon-coach:dsc-archivist` | haiku | Bash, Glob |

- Agent 도구로 부릅니다. 요청은 아래 형식의 짧은 블록 하나로 보냅니다.
- 서브에이전트는 **감독 세션이 가진 도구 안에서만** 도구를 받습니다(M0 실험 C).
- 실제 일은 이 스킬의 `scripts/` 안 스크립트가 합니다. 에이전트는 스크립트를 부르고 결과를 옮기기만 합니다.
  금지 사항(쓰기 위치, 주석 게이트, Logos 읽기 명령, 단계 확인)은 **스크립트 코드가 강제**합니다.
- 요청의 `scripts:`에는 이 스킬 폴더의 `scripts` 절대경로를 넣습니다(스킬을 불러올 때 표시되는 기본 폴더 + `/scripts`).
- `config:`는 `~/.config/dsc/dsc.config.json`입니다. 없으면 생략합니다.

## 2. 수집 에이전트 `dsc-collector`

### 요청
```
task: passage | commentary | syntax
week_dir: <주간 폴더 절대경로>
passage: <예: 요한복음 15:1-8>
scripts: <스킬 폴더>/scripts
config: <~/.config/dsc/dsc.config.json>
```

### 하는 일 (`scripts/dsc_collect.py`)
- `passage`: 아래 본문을 받아 `00_수집/passage.json`과 읽기용 `00_수집/본문_{본문}.md`로 저장합니다.

  | 항목 | 출처 | 교차 검증 |
  |---|---|---|
  | 새한글·새번역·공동번역 개정판·개역개정 | 대한성서공회 성경플랫폼 `bible.bskorea.or.kr/bible/{NKT·RNKSV·KCT·NKRV}/{책}.{장}` | 새번역·공동번역·개역개정은 구 읽기 화면 `www.bskorea.or.kr`와 글자 대조. 새한글은 두 번째 공식 출처가 없어 `single_source` |
  | ESV | `die-bibel.de/bibel/ESV/…` | `biblegateway.com`과 글자 대조 |
  | NA28 (신약) · BHS (구약) | `die-bibel.de/bibel/{NA28·BHS}/…` | — |

  - 사이트는 없는 역본을 요청받으면 **다른 역본을 조용히 돌려줍니다**(성서공회에 NA28을 요청하면 개역개정이 옴).
    그래서 응답의 성경 ID와 글자 종류(한글·헬라어·히브리어·영문)를 대조하고, 다르면 `missing`에 넣습니다.
  - 웹 요약을 거치는 WebFetch를 쓰지 않습니다. 본문은 받은 글자 그대로 저장합니다.
  - 원어 구문(clause) 목록: 헬라어 `·` `.` `;`, 히브리어 아트나흐·소프 파숙에서 **기계적으로** 나눕니다(`method: 문장부호 기계 분할`). 구문 번호는 `장.절` + 알파벳(예: `4.7a`).
  - 시편 표제는 `superscriptions`에 따로 남깁니다. 원어와 개역개정의 절 수가 다르면 `notes`에 알립니다. 합쳐진 절(예: 25-26)은 `combined_verses`에 남깁니다. 요청 범위가 장 끝을 넘으면 `missing`에 적습니다.
  - 앞·뒤 페리코페: 개역개정 소제목을 경계로 `adjacent_pericopes.before / after`에 모읍니다. 본문이 소제목 중간에서 끝나면 뒤 페리코페 제목에 「(이어짐)」을 붙입니다.
- `syntax`: 감독이 쓴 `00_수집/구문분석_초안.json`을 수집본과 대조해 `00_수집/syntax.json`에 절 단위로 합쳐 넣고 초안을 지웁니다(`references/syntax-analysis.md`).
  - 막는 것: 원어 낱말을 이은 것이 수집본 그 절과 다름, 새한글·ESV 조각이 수집본에 없음, 범위 밖 절, 구문 ID·라벨 계열·들여쓰기 형식.
  - 실패하면 아무것도 바꾸지 않고 `problems`(문제 목록)를 돌려줍니다. 분해 표기·해설 문장 수는 `warnings`입니다.
- `commentary`: `progress.json`의 `current_stage`가 **4·5·6·7B·8·9**일 때만 수집합니다. 그 밖의 단계에서는 `refused`입니다.
  - ① 설정의 `materials_dirs` 안 `.md`·`.txt`(③ `md_commentary_glob` = `B_*.md` 포함) — 제목(#) 단위로 범위 안 구절을 다루는 절만 발췌
  - ② Logos 수집본 — 브리지의 `excerpt`만 호출(`library`·`books`·`excerpt` 밖의 명령은 코드가 막음)
  - 저장: `00_수집/주석/{B·자료·Logos}_{자료명}_{본문}.md`. 첫머리 frontmatter에 출처(종류·파일·서명·저자·절 제목·발췌 여부·수집 시각)를 적습니다.
  - 웹에서 주석을 찾지 않습니다. PDF·EPUB 원본에서 뽑지 않습니다.
  - 자료 폴더 안의 자기적용 파일(신판·구판 번호 모두), `private: true` 파일, `S_YYYYMMDD` 주간 폴더 안 파일은 건너뜁니다(자기적용이 주석 수집본으로 새지 않게).

### 돌려주는 것 (이것만)
```
status: ok | partial | failed | refused
saved: [<경로>, ...]
counts: {translations: n, original: n, clauses: n, commentary: n}
cross_check: {<역본>: <match|differ|single_source|unavailable>}
sources: [<주석 출처 이름>, ...]
missing: [<빠진 항목>, ...]
reason: <refused일 때>
```
- **주석 내용·요약·해석을 돌려주지 않습니다.** 개수와 경로, 출처 이름만 돌려줍니다.
- 본문을 지어내지 않습니다. 못 찾으면 `missing`에 넣습니다.
- `cross_check`가 `differ`이면 감독은 설교자에게 「두 출처가 다른 절이 있습니다」 한 줄과 절 번호만 알립니다(어느 쪽이 옳은지는 설교자 제공 본문이 정합니다).

### `passage.json` 모양
```json
{
 "dsc_version": "1.0.0", "reference": "고린도후서 4:1-18",
 "book": {"ko": "고린도후서", "usfm": "2CO", "en": "2 Corinthians", "testament": "NT"},
 "range": {"start": [4, 1], "end": [4, 18]}, "collected_at": "…",
 "translations": {"NKT": {"name": "새한글", "abbr": "NKT", "source": "bible.bskorea.or.kr", "urls": ["…"],
                          "copyright": "…", "method": "자동 fetch",
                          "verses": [{"ref": "4:1", "text": "…"}], "headings": [{"before": "4:1", "title": "…"}],
                          "cross_check": [{"status": "single_source"}]}, "RNKSV": {}, "KCT": {}, "NKRV": {}, "ESV": {}},
 "original": {"NA28": {"…": "같은 모양"}},
 "clauses": [{"id": "4.7a", "verse": "4:7", "text": "…", "method": "문장부호 기계 분할"}],
 "adjacent_pericopes": {"before": {"title": "…", "range": "3:1-3:18", "source": "NKRV", "verses": []}, "after": {}},
 "missing": [{"item": "…", "reason": "…"}]
}
```

## 3. 기록보관 에이전트 `dsc-archivist`

### 요청
```
task: init | status | validate | advance_stage | render_stage3 | privacy
week_dir: <주간 폴더 절대경로>
scripts: <스킬 폴더>/scripts
config: <~/.config/dsc/dsc.config.json>
passage: <init일 때>
sermon_date: <init일 때 YYYY-MM-DD>
stage: <advance_stage일 때 올라갈 단계 · validate일 때 선택>
confirmed_by_preacher: true          # advance_stage일 때 필수
```

### 하는 일 (`scripts/dsc_archive.py` · `scripts/check_privacy.py`)
| task | 내용 |
|---|---|
| `init` | 주간 폴더·`00_수집/`·`progress.json`(`dsc_version: 1.0.0`, `current_stage: 0`)·`00_진행상황.md` 만들기. 구판 폴더(progress.json 없이 산출물이 있음)와, 설정 `vault_root` 바로 아래가 아닌 폴더는 거절 |
| `status` | 지금 단계, 단계별 파일, 수집 여부(본문·주석 개수) |
| `validate` | 파일명이 `stage-map.md`와 맞는지(구판 번호는 새 번호를 제안), YAML 필수 키(`yaml-schema.md`), 하이픈 키, 날짜 형식, `stage` 값, 단계 태그, 07A의 `private: true`. 이어서 `privacy` |
| `advance_stage` | `confirmed_by_preacher: true`일 때만 `current_stage`·`stage_entered`를 갱신. 되돌리기는 거절, 건너뛴 단계는 `issues`로 알림 |
| `render_stage3` | `03_원어관찰.json` → `03_원어관찰_{작업일}_{본문}.md`. 생성본이 마지막 생성 뒤 손으로 고쳐졌으면(해시 비교) 덮어쓰지 않고 `issues` |
| `privacy` | `check_privacy.py` — 7A 문장이 비공개 표시 없는 파일에 들어갔는지(아래 §5) |

### 돌려주는 것
```
status: ok | issues | refused
current_stage: <status·advance_stage일 때>
issues: [{file, problem, suggestion}, ...]
privacy: {errors: n, warnings: [...]}
reason: <refused일 때>
```

### 지키는 것
- **설교자가 쓴 내용을 고치지 않습니다.** 문제는 `issues`로 보고만 합니다.
- 직접 쓰는 파일은 `progress.json`, `00_진행상황.md`, `03_원어관찰_…md`(생성본)뿐입니다.
- `progress.json`은 `.progress.lock` 잠금 안에서 다시 읽고, 고유 임시 파일에 쓴 뒤 바꿔 끼웁니다. 관찰 작업창 서버(M4)도 같은 함수(`dsc_archive.progress_lock`·`write_progress`)를 씁니다.
- `render_stage3`는 같은 이름의 파일이 이미 있는데 생성 기록(해시)이 없거나 해시가 다르면 덮어쓰지 않습니다.
- 07A 파일은 frontmatter만 읽습니다. 비공개 점검은 7A 문장을 비교만 하고 **어디에도 출력하지 않습니다.**

## 4. 감독이 지키는 것
- 하위 에이전트의 결과를 설교자에게 전할 때, 해석을 덧붙이지 않습니다.
- 주석 게이트(SKILL.md §4.3)를 어기는 위임을 하지 않습니다. 설교자가 Stage 4(1차청중)로 가자고 하면 **먼저** `advance_stage`(stage: 4), **그다음** `commentary`를 맡깁니다.
- 위임이 실패하면 설교자에게 한 줄로 알리고, 대화로 대신 진행할 수 있게 합니다.
- `confirmed_by_preacher: true`는 감독이 붙이는 표시입니다. 스크립트는 설교자의 확인을 직접 검증하지 못합니다. 그래서 감독은 설교자가 이번 대화에서 「다음 단계」를 **말로 확인한 직후에만** 이 값을 붙입니다.
- 에이전트는 요청 값을 작은따옴표로 감싸 명령에 넣고, 셸 특수문자가 든 값은 거절합니다. 본문 범위·경로에 그런 문자를 넣지 않습니다.

## 5. 비공개 점검 규칙 (`check_privacy.py`)
- 07A 파일에 `private: true`와 tags의 `private`가 있어야 합니다.
- 7A 문장(공백 빼고 15자 이상)이 다른 파일에 그대로 있으면, 그 파일도 비공개 표시가 있어야 합니다.
  - md: `private: true` · HTML: `<meta name="dsc-private" content="true">`
  - 설교자가 그 문장을 공개 원고에 넣기로 **확인했으면** md `shared_by_preacher: true` · HTML `<meta name="dsc-shared-by-preacher" content="true">`. 오류 대신 안내로 바뀝니다.
- 7A 이전 단계(01~06)·`passage.json`에 이미 있던 문장은 7A 문장으로 보지 않습니다(성경 인용·앞 단계 기록).
- `00_수집/`(작업 기록 `ask_log.jsonl` 등)에 7A 문장이 있으면 경고입니다.
- 구판 주간(06A)은 같은 방식으로 보되 경고로만 냅니다.
