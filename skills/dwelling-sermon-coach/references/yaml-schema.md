# YAML 규격 (v1.0.0)

모든 산출물 md의 frontmatter는 이 규격을 따릅니다.
기록보관 매니저(`dsc-archivist`)의 `validate`가 이 표로 검사합니다.
템플릿 전문은 `output-templates.md`에 있습니다.

## 1. 공통 규칙
- 키는 모두 **snake_case**입니다. 하이픈 키(`sermon-date`, `big-idea`, `date-compiled`)는 쓰지 않습니다.
- 날짜는 `YYYY-MM-DD`입니다.
- `preacher`·`church`는 설정(`~/.config/dsc/dsc.config.json`)에서 채웁니다.
- 구판(v0.4) 파일은 검사하지 않습니다. `dsc_version`이 없는 파일은 읽기 전용입니다.

## 2. 공통 키 (모든 단계 파일)

| 키 | 필수 | 값 |
|---|---|---|
| `dsc_version` | ● | `1.0.0` |
| `date` | ● | 작업일 (01은 설교일과 같아도 됨) |
| `sermon_date` | ● | 설교 예정일 |
| `text` | ● | `성경책 장:절` |
| `stage` | ● | `0`~`9` (7A·7B는 `7`) |
| `session` | ● | 정식 이름 (`stage-map.md`) |
| `preacher` | ● | 설정값 |
| `church` | ● | 설정값 |
| `status` | ● | `dwelling` 또는 `ready` |
| `tags` | ● | `dwelling-sermon-coach`, 본문책 영문 슬러그, 단계 태그 |

## 3. 단계별 추가 키

| 파일 | 추가 필수 키 | 단계 태그 |
|---|---|---|
| `01_본문만남` | — | `stage-1-encounter` |
| `02_동행일지` | — | `stage-2-dwelling` |
| `03_원어관찰_…md` | `generated: true` | `stage-3-original` |
| `03_나의번역_…md` | `generated: true`; `stage: 3`, `session: 나의번역` | `stage-3-original` |
| `04_1차청중` | — | `stage-4-audience` |
| `05_맥락관찰` | — | `stage-5-context` |
| `06_묵직한단어` | `keyword` | `stage-6-keyword` |
| `07A_자기적용` | **`private: true`** | `stage-7a-self`, `private` |
| `07B_회중적용` | — | `stage-7b-congregation` |
| `08_원고점검` | `keyword`, `big_idea` | `stage-8-review` |
| `설교_…_묵상종합` | `date_compiled`, `keyword`, `big_idea` (`date`·`stage`·`session` 대신), `status: ready` | `묵상종합` |
| `설교_…_개요` | `keyword`, `big_idea`; `stage: 9`, `session: 설교개요` | `stage-9-outline` |

- `02_동행일지`에는 선택 키 `scenes`(설교자가 나눈 장면 수, 정수)를 붙일 수 있습니다. 필수가 아니며 `validate`는 검사하지 않습니다 (v1.0.2, v1.0.1의 `01_본문만남`에서 옮김).
- `stage3_private: true`(설정, 예전 이름 `stage3_apply_private`)이면 `03_원어관찰_…md`·`03_나의번역_…md`에도 `private: true`를 붙입니다.
- 설교자가 7A 문장을 개요에 넣었으면 개요에도 `private: true`를 붙입니다. `private: true` 파일은 카카오톡으로 자동 발송하지 않습니다.
- 7A 문장을 공개 원고(개요·묵상종합·원고·낭독본 등)에 넣기로 설교자가 **확인했으면** `shared_by_preacher: true`를 붙입니다. 비공개 점검(`check_privacy.py`)이 오류 대신 안내로 냅니다.
- HTML은 frontmatter 대신 `<head>`의 메타로 표시합니다: `<meta name="dsc-private" content="true">` · `<meta name="dsc-shared-by-preacher" content="true">`.

## 4. 검사 실패 예
- 07A에 `private: true`가 없음 → **오류** (가장 중요)
- `sermon-date`처럼 하이픈 키 → 오류, `sermon_date`로 고치도록 제안
- 파일명 번호와 `stage` 값이 다름 → 오류
- 설교자가 쓴 본문 내용은 검사하지 않습니다.
